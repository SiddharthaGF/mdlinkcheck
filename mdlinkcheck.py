#!/usr/bin/env python3
"""Report the relative links in a markdown file whose target does not exist.

Only local relative targets are checked. URLs, `mailto:`, `tel:`, `data:` and bare
fragments belong to somebody else's problem, so they are skipped silently.

Scope, stated so a reader is not misled: inline links and images are checked,
as are reference-style links and their definitions. Heading anchors are not
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

# `![alt](target)` and `[text](target)`. The title that may follow the target inside the
# parentheses is deliberately not captured: it never affects whether the target exists.
LINK = re.compile(r"!?\[[^\]]*\]\(\s*(<[^>]*>|[^\s)]+)[^)]*\)")

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


def iter_targets(text: str):
    """Yield `(line_number, target)` for every inline link in `text`, external ones excluded."""
    for match in LINK.finditer(strip_code(text)):
        target = match.group(1).strip("<>")
        if EXTERNAL.match(target):
            continue
        yield text.count("\n", 0, match.start()) + 1, target


def iter_definitions(text: str):
    """Yield `(line_number, target)` for every reference definition, external ones excluded.

    A definition is reported on the line it is defined, not where it is used, because that is the
    line a reader has to edit to fix it.
    """
    for match in DEFINITION.finditer(strip_code(text)):
        target = match.group(2).strip("<>")
        if EXTERNAL.match(target):
            continue
        yield text.count("\n", 0, match.start()) + 1, target


def resolve(base_dir: str, target: str) -> str:
    """Strip the fragment and query, then resolve against `base_dir`."""
    path = target.split("#", 1)[0].split("?", 1)[0]
    return os.path.normpath(os.path.join(base_dir, path))


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
    return sorted(broken)


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
