# Releasing

## The rule

**Merging accumulates. Publishing is a separate human decision.**

Merging a pull request into `main` never announces anything. It moves the line forward, and that is
all. The Release workflow reacts to the merge by working out what a release *would* contain and
posting it on a tracking issue. It creates no tag, no commit and no release, and the job that does it
has no permission to.

A maintainer reads the tracking issue and, when the accumulated work is worth shipping, dispatches
the workflow by hand. That dispatch is the decision.

## The two runs

| Run | Trigger | What it does | Permissions | Result |
| --- | --- | --- | --- | --- |
| `preview` | `push` to `main` | `semantic-release -c releaserc.toml version --print`, then `towncrier build --config towncrier.toml --draft --version <v>` | `issues: write` | A comment on the tracking issue. **Nothing is written to the repository.** |
| `cut` | `workflow_dispatch` | `towncrier build --version <v> --yes`, then `git add -A`, then `semantic-release -c releaserc.toml version --no-changelog` | `contents: write` | Tag `vX.Y.Z`, the changelog, a GitHub release |

`--print` is a dry run: it computes the version and exits without writing, committing, tagging,
pushing or releasing. That is the entire design of the preview job, and it is why the job needs no
`contents: write`. The preview finds the single open issue labelled `status:pendiente`, creating it
if it does not exist, and comments on it.

The cut runs in this order, and the order is the design:

1. Compute the version with `--print`. Writes nothing.
2. Refuse if it equals the last published tag, rather than create a duplicate.
3. `towncrier build --version <v> --yes`. Rewrites `CHANGELOG.md` and **deletes** the fragments it
   consumed — that deletion is what starts the next release's accumulation.
4. `git add -A`. Load-bearing; see below.
5. `semantic-release version --no-changelog`. Commits, tags, pushes, creates the release.
6. Compare the tag the releaser created against the version towncrier wrote into the changelog, and
   fail on a mismatch.

Step 3 has to come before step 5 because the releaser's commit *is* the release commit, and it
commits whatever is in the index. If towncrier ran afterwards, `CHANGELOG.md` would be left modified
in a runner about to be discarded and the tag would point at a commit whose changelog still
described the previous release.

Step 6 exists because the releaser computes the version a second time, and the two computations
have to agree. If they ever do not, the published changelog describes a version that was not
released — a green run that lies, which is the specific failure this repository keeps building
guards against.

## Why there are no release-candidate tags

There used to be one. A releasable merge minted `v1.0.6-rc.1` and a manual cut finalized it. The
tags turned out to be incompatible with a correct changelog, and not in a way any setting could fix.

**Mechanism.** `python-semantic-release` builds its changelog in
`semantic_release/changelog/release_history.py`. It walks history from `HEAD` with
`repo.iter_commits("HEAD", topo_order=True)`, looks up each commit in a `commit sha -> tag`
dictionary, and opens a new release section whenever a commit matches one. A tag is therefore a
release boundary: it decides where one version's notes stop and the next one's begin. This is
python-semantic-release behaviour, not this repository's configuration, and you can read it in the
installed source.

**What it did here.** The candidate tags were not releases, and the tool could not tell:

| Tag | On commit | Effect |
| --- | --- | --- |
| `v1.0.6-rc.1` | `4a35a8a` (#28) | its entry went to a section that is never published |
| `v1.0.6-rc.2` | `73c2596` (#30) | its entry did the same, and being `HEAD` it left the `v1.0.6` section with no commits at all |

The version number itself was never wrong. The cut found three commits since `v1.0.5` and computed
`1.0.6` correctly; only the changelog rendering used a narrower range. That is why the release
looked right and its notes were empty at the same time. The published `v1.0.6` section had no
entries.

Reproduced against a real 10.7.0 with this repository's configuration:

| Candidate tags present | Entries under `## v1.0.6` |
| --- | --- |
| `rc.1` only | 1 — #28 lost |
| `rc.1` and `rc.2` | 0 — both lost |
| none | 2 — both present |

**The fix is two-sided, because the tags cannot be repaired and should not need it.**

`towncrier` builds the changelog from files in `newsfragments/` and never reads git history, so
there is no boundary to get wrong. And the preview no longer creates a tag, so it cannot create a
false boundary in the first place. The tracking issue replaced the candidate tags as the signal that
work is waiting.

**The two candidate tags still in the history are not to be deleted.** Both are ancestors of
`v1.0.6`, so they sit on the far side of the boundary and no future changelog can reach them. You
can confirm it:

```console
$ git merge-base --is-ancestor v1.0.6-rc.2 v1.0.6 && echo "behind the boundary"
```

A published tag is never deleted. See "Reverting".

## How a change reaches the changelog

A news fragment: one small file in `newsfragments/`, named `<pull request number>.<type>`.

```
newsfragments/28.fix.md      →  "A linked image's outer target is never checked"
newsfragments/30.feat.md     →  "Read a target with spaces"
```

The fragment **is** the changelog. Towncrier reads those files and nothing else, so an entry that was
never written does not exist. It cannot be derived from the commit log afterwards, which is the whole
reason this mechanism replaced the one that was broken: the previous changelog was derived, and
derivation lost entries silently.

The types match the commit prefixes this repository already uses, so a fragment and its commit read
the same way:

| Type | Section heading | In the changelog |
| --- | --- | --- |
| `feat` | Features | published |
| `fix` | Bug Fixes | published |
| `doc` | Documentation | published |
| `removal` | Deprecations and Removals | published |
| `chore` | Other Tasks | **not published** — `showcontent = false` |
| `misc` | Miscellaneous | published |

A change nobody using the tool could observe takes `chore`. Its fragment records that the change
happened without printing a line in the changelog, which is the point: the changelog is for the
person using the tool, and "tidied CI" is noise in it.

Two settings in `towncrier.toml` keep the naming honest. `issue_pattern = "\\d+"` means a fragment
named after a branch, or `fix.fix`, fails the build instead of publishing a link to a pull request
that does not exist. `ignore = []` — configuring the list at all, even empty, makes towncrier fail
on invalid filenames rather than ignoring them.

`towncrier create <n>.<type>` writes the file for you.

## Behaviors that will surprise you

### A preview that reports a version and then does nothing

You push a `fix:`, the preview reports `1.0.7` and posts a changelog to the tracking issue, and no
tag appears. That is the model. The preview answers "what would a cut release?", which is the
question worth answering before deciding. It is also why the job holds `issues: write` and not
`contents: write`: it is built so it cannot publish by accident.

### A change nobody can observe produces no preview

A `chore:` or `ci:` merge reports nothing pending. The releaser computes the level bump from commit
subjects, and a push whose new commits are all excluded types computes `NO_RELEASE`; "no version"
stays "no version". The counter counts releasable changes, not merges, which is what makes it worth
reading.

Note that the list of types excluded from the *version bump* and the list of types whose fragments
are *published* are related but not identical. A `docs:` commit does not move the version, and a
`doc` fragment would be published if one were added. See `releaserc.toml` and `towncrier.toml`.

### A cut with nothing pending fails instead of doing nothing quietly

Dispatch a cut with no releasable work and it exits non-zero with `cut refused: nothing releasable
since v1.0.6, so 1.0.6 would be a duplicate tag`. A red run is recoverable. A green run that reports
success while writing nothing is the failure this repository keeps guarding against: an earlier
version of the report step printed `1.0.0 as v1.0.0` on a run that had really minted `v1.0.6-rc.1`.

### A release can ship with an empty changelog section

**Nothing enforces that a fragment exists.** The pull request template asks for one and the checklist
below says to check for one, but no CI step fails a pull request that forgot. A cut then writes a
version heading with nothing under it.

This is the same failure the candidate tags caused, arriving by a different route: those swallowed
entries silently, a forgotten fragment omits them silently. The fix is a `towncrier check` step in
`ci.yml` and it has not been built. If you cut a release and find an empty section, that is why.

## Neither run uses the GitHub Action

Both jobs call the CLI directly. The action was here because the preview needed `--as-prerelease`
and the action has no arbitrary-argument passthrough. Its complete input list is `config_file`,
`directory`, `github_token`, `git_committer_name`, `git_committer_email`, `no_operation_mode`,
`ssh_public_signing_key`, `ssh_private_signing_key`, `strict`, `verbosity`, `prerelease`,
`prerelease_token`, `force`, `commit`, `tag`, `push`, `changelog`, `vcs_release`, `build`,
`build_metadata`. GitHub Actions **warns** on an unrecognised input and continues, so passing one
anyway produces a green run doing the wrong thing. That is not hypothetical: run 36387475484 minted
`v1.0.6-rc.1` and reported `1.0.0 as v1.0.0`, because the flag was passed as an input the action
does not have.

The preview no longer releases, so it does not need the flag, and with the asymmetry gone neither job
has a reason to run a container to call a CLI that two `pip install` lines already provide.

Two details of calling the CLI that are easy to "fix" wrongly:

- `-c` is a **top-level** flag and must precede the subcommand.
  `semantic-release version -c releaserc.toml` fails with `Error: No such option '-c'`. Verified by
  execution against a real 10.7.0 install, not by reading the documentation. The same is true of
  `-vv`, and `--noop` is not a `version` subcommand option in 10.7.0 at all.
- `semantic-release version` already performs the whole sequence — version stamping, changelog,
  build, commit, tag, push, VCS release. There is no `semantic-release publish` after it.

## The toolchain, and who may do what

- **One Python for the repository.** `actions/setup-python` pinned at
  `5fda3b95a4ea91299a34e894583c3862153e4b97 # v7`, the same sha `.github/workflows/ci.yml` uses,
  with `python-version: '3.13'`. A release cannot behave differently from the tested code.
- **Exact pins.** `python -m pip install "python-semantic-release==10.7.0" "towncrier==26.9.0"` — no
  ranges, and not touched by Dependabot, so they do not move on their own.
- **`GH_TOKEN` in the environment**, because `releaserc.toml` declares
  `[semantic_release.remote] token = {env = "GH_TOKEN"}`. The variable name is part of the config.
- **The permission split is the security property, not a detail.** `preview` holds `issues: write`
  and not `contents: write`, so it cannot create a tag, a commit or a release even by accident; it
  reads the repository and writes a comment. `cut` holds `contents: write` and not `issues: write`.
  Neither grant is workflow-wide.
- **Committer identity.** The release commit is authored by `git config --local user.name` /
  `user.email` set in the checkout, not by PSR's own default (`semantic-release <semantic-release>`,
  which is no account at all) and not by the action's documented example (which resolves to the
  `actions` *organization*). `--local` outranks the global config.
- **One concurrency group, both jobs, keyed on the ref, `cancel-in-progress: false`.** A preview and
  a cut can never overlap, and a release half way through is not cancelled by the next event.
- **The sha reset.** Both jobs run `git reset --hard ${{ github.sha }}` after checkout, so the branch
  is forced to the workflow's own sha. Without it a push that landed while the run sat in the queue
  would be swept into a release nobody reviewed.

## The tag invariant

**Every tag this repository creates is `vX.Y.Z`. Nothing else is ever created.** There are no
prerelease tags any more; see "Why there are no release-candidate tags".

Two settings in `releaserc.toml` — `tag_format = "v{version}"` and `add_partial_tags = false` —
enforce it. The second keeps the moving `v1` and `v1.0` aliases off: they were never actually
created by the tool across four observed runs, and nothing adopts this repository by ref, so
shipping them on trust would only add two tags that lie about the shape of the history.

A tag that is neither is a bug in `releaserc.toml`, not an accident to clean up later.

## Before you merge

- [ ] **The change has a fragment in `newsfragments/`, named `<this pull request number>.<type>`.**
      Nothing will complain if it is missing, and nothing will put the change in the changelog.
- [ ] The fragment says what changed for the person using the tool, not how the code changed.
- [ ] The type matches the commit prefix: `fix:` gets a `fix` fragment, `feat:` gets a `feat`.
- [ ] The pull request title is a Conventional Commit. That title is the commit message on `main`,
      so it is what the version bump is computed from.
- [ ] A breaking change carries `BREAKING CHANGE:` in the body, and the title says what broke. This
      is what moves the major while the version is still zero (`major_on_zero = true`).
- [ ] `main` is green: CI passed on the merge, not on a branch from three commits ago.

## Cutting a release

1. Open the tracking issue — the one labelled `status:pendiente`. Read the version it proposes and
   the changelog it renders.
2. Read it critically. That changelog is what the cut will write, produced by the same tool and the
   same fragments. If a section is empty, the fragment is missing and no cut will fix it.
3. **Actions** → **Release** → **Run workflow**, with the branch selector on `main`. The workflow
   refuses any other ref and says so.
4. Read the run log. It ends in one of two lines:
   - `cut a release: 1.1.0 as v1.1.0: <link>` — done.
   - `cut refused: nothing releasable since v1.0.6, ...` — nothing was cut, and the run failed on
     purpose. Read why.
5. Open the tag on GitHub and read the release body before announcing anything.
6. Announce, with the release link.

Between steps 3 and 5, nothing is public. That gap is the entire point of the model.

## Reverting

**Never delete a tag.** Not to undo a bad release, not to redo a number, not to clean up a mistake.
A released tag is a promise that a version exists; deleting it makes every clone that already
fetched it fail, and it erases the only record of what shipped.

Revert forward: open a pull request with a `fix:` fragment describing the breakage, merge it, and
let the next cut carry the correction. The version then reads `v1.1.1` after a `v1.1.0` that shipped
a bug, which is the truth — the bug shipped, and the fix shipped after it.

The two candidate tags in the history follow the same rule, and additionally they are behind the
`v1.0.6` boundary where no changelog can reach them. Deleting them would only make the history
harder to read.

## Adopting this flow in another project

1. Start from `releaserc.toml` and `towncrier.toml` in this repository. Copy them, then delete what
   your project does not have and **re-justify every comment you keep** — a copied comment that no
   longer describes the line below it is worse than no comment.
2. Point `[semantic_release.branches.<name>]` at your default branch and keep `prerelease = false`.
3. Keep `add_partial_tags = false` unless something genuinely consumes a `v1` alias.
4. Keep `parse_squash_commits = false` and `ignore_merge_commits = true` if your repository
   squash-merges. They are not generic: with `parse_squash_commits = true`, GitHub puts the
   branch's whole commit list in the squash body and the releaser re-attributes already-released
   fixes to whichever pull request merged last. This is not hypothetical — it produced a wrong
   changelog entry here in v1.0.2.
5. `towncrier.toml` rather than `pyproject.toml` if your project has no `pyproject.toml`. Towncrier
   accepts either, and a project that is not a distributed package has no `[project]` table to put a
   `[tool.towncrier]` block in.
6. Put the fragment requirement in the pull request template **and enforce it in CI** with a
   `towncrier check` step. This repository asks for a fragment and does not enforce one, which is a
   known gap; do not copy that part.
7. Set permissions deliberately: `contents: read` at workflow level, `issues: write` on the preview
   job, `contents: write` on the cut job, and nothing more.
8. Verify the flow end to end before trusting it — extract the `run:` blocks out of the workflow file
   and execute them against a scratch clone. An earlier version of this change was verified by
   retyping the logic into a test script; the edit to the workflow silently did not land, and the
   broken version shipped.
