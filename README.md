# mdlinkcheck

Report the relative links in a markdown file whose target does not exist. Standard library only, no
dependencies, no configuration.

```console
$ python3 mdlinkcheck.py README.md
README.md:12: broken link: CHANGELOG.md
$ echo $?
1
```

## Usage

```bash
python3 mdlinkcheck.py README.md docs/*.md   # exit 1 if anything is broken
python3 mdlinkcheck.py README.md --quiet     # only the exit code; prints nothing
```

| Exit code | Meaning |
| --- | --- |
| `0` | Every local relative link resolves |
| `1` | At least one broken link, or a file that could not be read |

## What it checks, and what it does not

It parses inline links and images: `[text](target)` and `![alt](target)`. For each one whose target
is a **local relative path**, it resolves the target against the markdown file's own directory — never
against your working directory, so the answer is the same from anywhere — and reports it if nothing is
there. A target that is a directory counts as satisfied, and a `#fragment` or `?query` is stripped
before the check.

It deliberately ignores anything that is not a local path: `http://`, `https://`, `mailto:`, `tel:`,
`data:`, protocol-relative `//host/path`, and bare `#anchor`. Those are somebody else's problem, and
checking them would make the tool a network client.

Two limitations worth stating rather than discovering:

- **Reference-style links are not parsed.** `[text][ref]` and its `[ref]: target` definition are left
  alone, so a broken reference-style link is not reported. Only the inline form is checked.
- **Heading anchors are not resolved.** A `#fragment` is stripped and the file is checked for
  existence; whether the heading is actually there is not verified.

## Releases

The version is the tag, and the tag is made by a machine. Every push to `main` that carries a
`feat:`, `fix:` or `perf:` commit produces a `vX.Y.Z` tag and a GitHub release, with a `CHANGELOG.md`
maintained for you:

```console
$ git tag -l
v1.0.0
```

Two things about it are worth knowing before you add a commit:

- **The commit subject is the version signal**, so the title convention the pull request policy
  already enforces is what drives the bump. A subject that is not conventional produces no release.
  That is why the repository is squash-merge only: a merge commit would carry no conventional
  subject and every merge would look like an empty patch.
- **Merging is publishing.** There is no pull request between the merge and the release, by design.
  Nothing is published to PyPI, and nothing adopts this repository by ref, so there is no floating
  `v1` to keep honest.

`CHANGELOG.md` lists only what a reader cares about: `chore`, `ci`, `test`, `style` and `refactor`
commits are excluded, because a reader is not looking for them in a changelog.

The release itself is made by the official
[`python-semantic-release` action](https://github.com/marketplace/actions/python-semantic-release),
pinned by commit. It runs in a container, so this repository needs no Python releaser installed and no
version of it pinned here. The commit it pushes is authored by the GitHub Actions bot rather than by
the tool's own default, which is not an account.

## Running the tests

```bash
python3 -m unittest discover
```

Eleven tests, no network, nothing written outside a temporary directory. They cover the target
filtering, line numbers in the report, fragments and queries, directory targets, resolution against
the file's own directory, and both exit codes.

## Why this exists

This repository exists to consume [`ailuracollective/actions`](https://github.com/ailuracollective/actions)
from the outside. The tool itself is deliberately small: it is a real, working utility, and it is small
because the point of the repository is what runs against it in [`.github/workflows/policy.yml`](.github/workflows/policy.yml)
— three published composite actions that judge every pull request, adopted by path, with no checkout
of the code under review.

If a finding about those actions turns up here, it belongs in their repository, not in this one.
