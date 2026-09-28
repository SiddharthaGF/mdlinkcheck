# Pull request

## Summary

What changes, and why. Link the issue this closes with a closing keyword, for example `Closes #12`.

## News fragment

Every change that a user of this tool could observe needs a fragment in `newsfragments/`, named
`<pull request number>.<type>` — for example `42.fix` or `42.feat`. One line of plain text saying
what changed for the person using the tool, not how the code changed. The file is the changelog: it
is what `towncrier` writes into the next release, and unlike the commit log it cannot be derived from
anything, so if it is not written here it does not exist.

The types are `feat`, `fix`, `doc`, `removal`, `chore` and `misc`, matching the commit prefixes this
repository already uses. A change nobody can observe takes `chore`, whose text is not published.

Write it after the pull request is opened and you know the number; `towncrier create <n>.<type>`
writes the file for you.

## How it was tested

The commands you ran and what you saw. A claim that is not reproducible is not a test.

## Notes for the reviewer

Anything you would have wanted to know before reading the diff: a decision you reversed, a risk you
accepted, a part you are unsure about.
