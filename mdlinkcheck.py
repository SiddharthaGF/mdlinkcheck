#!/usr/bin/env python3
"""Report the relative links in a markdown file whose target does not exist.

Only local relative targets are checked. URLs, `mailto:`, `tel:`, `data:` and bare
fragments belong to somebody else's problem, so they are skipped silently.

Scope, stated so a reader is not misled: inline links and images are checked,
as are reference-style links and their definitions. A linked image is two
links, and both of its targets are checked. Heading anchors are not
resolved. A target that exists is enough, whatever it points at. Code spans
and fenced blocks are not text, so a syntax example inside them is not a link.

Targets resolve against the markdown file's own directory, never the working
directory, so the tool gives the same answer from anywhere.

Usage: mdlinkcheck.py FILE... [--quiet]
Exits 1 if any link is broken, 0 otherwise.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from urllib.parse import unquote

# A reference definition, `[label]: target`, possibly indented inside a list item. The label is
# captured whole so a case difference between the use and the definition is the caller's problem,
# not this tool's: the check is whether the target exists, not whether the reference resolves.
DEFINITION = re.compile(r"^[ ]{0,3}\[([^\]]+)\]:[ \t]*(\S+)", re.MULTILINE)

# Schemes and shapes that are not this file's business. A bare `//host/path` is protocol
# relative, and `#frag` points inside the same document.
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)

# Fenced blocks and inline spans, removed before parsing: a document that documents link
# syntax contains link syntax, and reporting that as a broken link is a false positive.
FENCE = re.compile(r"^ {0,3}(?:```|~~~).*?^ {0,3}(?:```|~~~)\s*$", re.MULTILINE | re.DOTALL)
SPAN = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)


def blank(match: "re.Match[str]") -> str:
    """Replace a match with spaces, keeping its newlines so line numbers survive."""
    return re.sub(r"[^\n]", " ", match.group(0))


def strip_code(text: str) -> str:
    """Blank out fenced blocks and inline code spans, preserving every offset and newline."""
    return SPAN.sub(blank, FENCE.sub(blank, text))


def read_target(text: str, open_paren: int) -> tuple[str, int]:
    """Return the target of the link whose `(` is at `open_paren`, and the index after its `)`.

    Parentheses inside the target are balanced rather than terminated at: `file(1).md` is one target,
    and stopping at the first `)` would report a file that exists as broken. An escaped paren does
    not open a level. An unterminated link yields whatever was read and the end of the text.
    """
    depth = 1
    index = open_paren + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1 : index].strip(), index + 1
        index += 1
    return text[open_paren + 1 :].strip(), len(text)


def read_label(text: str, open_bracket: int) -> int:
    """Return the index of the `]` matching the `[` at `open_bracket`, or -1 if there is none.

    Brackets are balanced rather than matched by pattern, because a label may contain brackets of
    its own: the label of a linked image is `![badge](img.png)`, and any character class that stops
    at the first `]` truncates it. A backslash escapes the next character, as in a target, so an
    escaped bracket neither opens nor closes a level.
    """
    depth = 1
    index = open_bracket + 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def iter_link_starts(text: str):
    """Yield `(index of '[', index of '(')` for every inline link or image in `text`.

    Both indices are yielded because they answer different questions: the `(` is where the target
    starts being read, and the `[` is where the line number comes from, since a reader fixes a
    broken link on the line its label opens. The two coincide for a link written on one line.

    An image needs no special case: `![alt](x)` and `[alt](x)` are the same shape here, a `[` a
    label and a `(`, and a missing image is as broken as a missing page.

    The scan resumes one character after the label's `[`, not after the target, and that is what
    makes a linked image yield both links. Resuming past the target of `[![b](img.png)](MISSING.md)`
    would skip the image, because the link's own label already contains it.
    """
    cursor = 0
    while cursor < len(text):
        index = text.find("[", cursor)
        if index == -1:
            return
        if index > 0 and text[index - 1] == "\\" and text[index - 2 : index - 1] != "\\":
            # An escaped `[` is a literal bracket, not the start of a label. The one before it has to
            # be an unpaired backslash: `\\[x](y)` writes a backslash and then a real label.
            cursor = index + 1
            continue
        close = read_label(text, index)
        if close == -1 or close + 1 == len(text) or text[close + 1] != "(":
            # No label, or no target after it, so not a link. Step over the bracket and keep
            # looking: the bracket may still be part of a longer label further along.
            cursor = index + 1
            continue
        yield index, close + 1
        cursor = index + 1


def iter_targets(text: str):
    """Yield `(line_number, target)` for every inline link in `text`, external ones excluded."""
    scanned = strip_code(text)
    for bracket, open_paren in iter_link_starts(scanned):
        raw, _ = read_target(scanned, open_paren)
        if raw.startswith("<"):
            # Wrapped in angle brackets, which is how a target with spaces is written.
            target = raw[1 : raw.find(">")] if ">" in raw else raw[1:]
        else:
            # Unwrapped, the target ends at the first space: anything after it is the title.
            target = raw.split()[0] if raw.split() else ""
        # An escaped paren was only escaped so it would not close the link, so it is a real paren in
        # the path: `[x](a\).md)` names `a).md`.
        target = clean(target.replace("\\(", "(").replace("\\)", ")"))
        if not target or EXTERNAL.match(target):
            continue
        yield text.count("\n", 0, bracket) + 1, target


def clean(target: str) -> str:
    """Drop the fragment and query, and decode percent-encoding: `[x](a%20b.md)` names `a b.md`."""
    return unquote(target.split("#", 1)[0].split("?", 1)[0])


def iter_definitions(text: str):
    """Yield `(line_number, target)` for every reference definition, external ones excluded.

    A definition is reported on the line it is defined, not where it is used, because that is the
    line a reader has to edit to fix it.
    """
    for match in DEFINITION.finditer(strip_code(text)):
        target = clean(match.group(2).strip("<>"))
        if EXTERNAL.match(target):
            continue
        yield text.count("\n", 0, match.start()) + 1, target


def resolve(base_dir: str, target: str) -> str:
    """Resolve an already-cleaned target against `base_dir`."""
    return os.path.normpath(os.path.join(base_dir, target))


def check_file(path: str) -> list[tuple[int, str]]:
    """Return `(line_number, target)` for every broken link in `path`, in file order."""
    with open(path, encoding="utf-8") as handle:
        text = handle.read()

    base_dir = os.path.dirname(os.path.abspath(path))
    found = list(iter_targets(text)) + list(iter_definitions(text))
    broken = [
        (line, target)
        for line, target in found
        # A directory counts as satisfied: linking to a folder is a legitimate target.
        if not os.path.exists(resolve(base_dir, target))
    ]
    # One report per line and target, because one is one thing to fix. A target is reachable more
    # than once by nesting now that a label may contain a link of its own, and `[a [b](x.md) and
    # c](x.md)` names the same missing file twice on the same line. Reporting it twice tells a
    # reader there are two problems where there is one, and the second copy names nothing the first
    # one did not already name.
    return sorted(set(broken))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", metavar="FILE", help="markdown file to check")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="report nothing; only the exit code says whether anything is broken",
    )
    args = parser.parse_args(argv)

    broken = 0
    for path in args.files:
        try:
            findings = check_file(path)
        except OSError as error:
            print(f"error::cannot read {path}: {error}", file=sys.stderr)
            broken += 1
            continue
        for line, target in findings:
            if not args.quiet:
                print(f"{path}:{line}: broken link: {target}")
        broken += len(findings)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
