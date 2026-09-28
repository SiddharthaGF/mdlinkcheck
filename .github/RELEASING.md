# Releasing

## The rule

**Merging accumulates. Publishing is a separate human decision.**

Merging a pull request into `main` never announces anything to a user. It only moves the line
forward: if the merge carries a releasable commit, the Release workflow tags a *release candidate*
and files it as a GitHub **prerelease**, which is invisible to anyone not looking for prereleases.
The actual `vX.Y.Z` release is made by a maintainer, by hand, from the Actions tab.

Why the change: under the previous model, merging was publishing, so there was no moment at which
someone could look at the accumulated work and decide *now*. A `chore:`-only push, a half-finished
feature merged to unblock someone, and a genuine bug fix all produced the same outcome — a released
tag — and the tag was the only artifact that recorded the decision. Now the decision is a run a
person started, and the run log says what it did.

## The two runs

| Run | Trigger | Command | Result |
| --- | --- | --- | --- |
| RC | `push` to `main` | `semantic-release -c releaserc.toml version --as-prerelease --no-changelog` | tag `v1.1.0-rc.N`, GitHub release marked as a prerelease |
| Cut | `workflow_dispatch` | `semantic-release -c releaserc.toml version` (via the action, `changelog: 'true'`) | tag `v1.1.0` computed from the last full release, normal GitHub release |

The cut does not promote the candidate. It recomputes the version from the last **full** release, and
the candidate tag is not an input to that computation. In
`semantic_release/version/algorithm.py` of 10.7.0, a plain `version` run has `prerelease` false, so
`latest_version` is resolved to the last full release (~line 319) rather than to the newest
`vX.Y.Z-rc.N` tag. A cut with `v1.0.5` and `v1.1.0-rc.1` in history reaches `1.1.0` by bumping
`1.0.5` with a minor bump. The path that *does* promote a prerelease — the
`if latest_version.is_prerelease:` guard at ~line 175, the `"Finalizing the prerelease version..."`
log it prints, and the `finalize_version()` it returns — is never entered on a cut, because the
version it tests is a full release by construction.

The numbers are identical either way, which is how the wrong mechanism stayed invisible for four
releases: the documented story and the real mechanism produce the same tag. Read the tags, not the
story. The guard and the unreachable log were read out of the installed 10.7.0 source; the numbers
come from `--print` runs against a real 10.7.0 install.

The flag difference is not cosmetic either. `--as-prerelease` converts the next version the tool was
going to calculate into a prerelease and leaves a `NO_RELEASE` alone. `--prerelease` would *force* a
version on every run, which is the behavior this model explicitly does not want.

### The cut absorbs everything after the candidate

**This is the single most important thing to know about the flow, and it is not a bug.**

**What happens.** You cut `v1.1.0-rc.3` expecting to publish exactly what `rc.3` covered. Since
`rc.3` was minted, a second feature was merged. The cut publishes `v1.1.0` **containing both
features**, and the changelog entry lists both. Observed against a real 10.7.0 install with tags
`v1.0.5` and `v1.1.0-rc.1`, a `feat` after the candidate, and a cut: the cut computes `1.1.0`, and a
subsequent RC run then produces `1.1.0-rc.2` — the second feature was absorbed into the same minor,
not promoted to a new one.

**Why.** The candidate tag is a **bookmark that says work has accumulated and is releasable**, not a
snapshot of what the cut will contain. The cut's scope is always the whole range from the last full
release to `HEAD`, because that is the range `latest_version` resolves to (see the mechanism above).

**How to think about it.** `rc.N` is a status light, not a build artifact. Reading `rc.3` as "this is
the release" and expecting the cut to be mechanical is the mistake; reading it as "the work is ready"
is the right model. If you need a hard boundary, dispatch the cut and read the log before announcing
— the changelog the cut writes is the authoritative list of what shipped.

**What it does not affect.** The number itself. Two `feat:` merges inside the same accumulation are
one `minor`, not two, so a late feature does not bump you to `v1.2.0`.

## The deliberate asymmetry: which run is an action and which is a command line

| Run | Uses | Why |
| --- | --- | --- |
| RC | `actions/setup-python` + `pip install "python-semantic-release==10.7.0"` + the CLI | the action cannot pass `--as-prerelease` |
| Cut | the pinned `python-semantic-release/python-semantic-release` action | the action *can* express what the cut needs, with no arguments at all |

The action's complete input list is `config_file`, `directory`, `github_token`,
`git_committer_name`, `git_committer_email`, `no_operation_mode`, `ssh_public_signing_key`,
`ssh_private_signing_key`, `strict`, `verbosity`, `prerelease`, `prerelease_token`, `force`,
`commit`, `tag`, `push`, `changelog`, `vcs_release`, `build`, `build_metadata`. There is no
arbitrary-argument passthrough, so `--as-prerelease` cannot be handed to it. Its `prerelease` input
is not a substitute: it maps to the CLI's `--prerelease`, which forces a version even when the level
bump is `NO_RELEASE` — that would make `rc.N` count pushes instead of changes and destroy the one
signal the design rests on.

So the RC run invokes the CLI directly, and the cut stays on the action, which is the tool's own
documented example for the one path that actually creates a real release. The asymmetry is the price
of the flag, paid once, on the run that cannot use the shortcut.

Two details of the direct invocation that are easy to "fix" wrongly:

- `-c` is a **top-level** flag and must precede the subcommand.
  `semantic-release version -c releaserc.toml` fails with `Error: No such option '-c'`. Verified by
  execution against a real 10.7.0 install, not by reading the docs. Same for `-vv` if you ever need
  it; and `--noop` is not a `version` subcommand option in 10.7.0 at all.
- `semantic-release version` already performs the whole sequence — version stamping, changelog,
  build, commit, tag, push, VCS release. There is no `semantic-release publish` after it.

### Guarantees the direct run has to reproduce

- **Toolchain.** `actions/setup-python` pinned at `5fda3b95a4ea91299a34e894583c3862153e4b97 # v7`,
  the same sha `.github/workflows/ci.yml` uses, with `python-version: '3.13'`. One Python for the
  repository: a release cannot behave differently from the tested code.
- **Pinned dependency.** `python -m pip install "python-semantic-release==10.7.0"` — exact, no range,
  no unpinned install, and not touched by Dependabot, so it does not move on its own.
- **`GH_TOKEN` in the environment**, because `releaserc.toml` declares
  `[semantic_release.remote] token = {env = "GH_TOKEN"}`. The variable name is part of the config.
- **Committer identity.** The action's two committer inputs do not exist on this path, so the RC run
  sets `git config --local user.name` / `user.email` in the checkout before releasing, with the same
  values the cut job passes to the action.

### The accepted tradeoff

The RC job holds `contents: write` and therefore resolves a dependency from the network while
holding the credential that can push tags. That is a real exposure, not a free choice, and it is
accepted deliberately: the alternative was leaving releases on an action that cannot express
`--as-prerelease`. The exact pin bounds it — the same code that produced the last four releases —
and the exposure exists only in a job that already has tag-write authority by necessity.

## Behaviors that will surprise you

### 1. The cut can almost never do nothing

**What happens, in practice.** You dispatch the cut while a candidate is pending and it always
releases. If the Report step prints `no release was made`, there is no pending candidate *and* nothing
releasable has landed since the last full release.

**Why.** The cut's range runs from the last full release, not from the candidate. So while a
candidate exists, the `feat:` that minted it is still inside that range, the level bump is at least
`MINOR`, and the tool has something to release. Observed against 10.7.0: with `v1.0.5`,
`v1.1.0-rc.1`, and only a `chore:` merged afterwards, the cut still computes `1.1.0`. The
"pending candidate left unfinalized" outcome documented here previously does not occur in this model.

**So read the `else` branch precisely.** It fires only when there is no candidate to cut *and* the
commits since the last full release are all excluded types (`chore:`, `ci:`, `docs:`, …). The
wording of the report line predates this correction and is kept stable as a human-facing contract;
it should be read as "nothing was releasable to publish", not "a candidate was stranded".

**On forcing a level: do not.** Both routes exist — the action's `force` input
(`prerelease` / `patch` / `minor` / `major`) and the CLI's `--prerelease` / `--patch` / `--minor` /
`--major`, the latter combinable with `--as-prerelease` for a forced *candidate*. Neither is
documented as forcing a finalization, and forcing is more likely to bump than to publish what is
accumulated: because the cut re-derives from the last full release, a forced `--minor` over an
accumulation that already contains a `feat:` is a number the tool would have arrived at on its own,
and a forced `--major` over the same accumulation cuts `v2.0.0` with `v1.1.0` never shipped. Use
them only for a candidate that must exist regardless of the bump, never to rescue a cut that did
nothing.

### 2. `rc.N` does not count pushes

**What happens.** You merged three pull requests and only two candidates appeared. Or you merged a
`docs:`-only pull request and no candidate appeared at all.

**Why.** `--as-prerelease` does not force a version. A push whose only new commits are `chore:`,
`ci:`, `test:`, `style:`, `refactor:` or a doc change computes `NO_RELEASE`, and "no version" stays
"no version" even in prerelease mode. The counter counts *releasable changes*, not merges.

**This is desirable, not a bug.** It is what keeps the candidate number meaningful: `rc.4` means four
releases' worth of pending work, not four pushes.

### 3. The changelog is written once, by the cut

**What happens.** Nothing surprising — but only because of how the two runs are configured, and the
reason is not obvious, so it is worth knowing.

**Mechanism.** The RC runs pass `--no-changelog`; the cut passes `changelog: 'true'` on the action,
which is its default, stated explicitly because it *is* the policy. The part that matters is why the
cut's changelog is complete rather than partial: it is the same resolution described under "The two
runs" — in the cut run `prerelease` is false, so PSR resolves `latest_version` to the last **full**
release — say `v1.0.5` — and not to the most recent candidate. The cut therefore writes an entry for
every commit accumulated since the last published version, not only the ones after `v1.1.0-rc.3`.
The candidates wrote nothing, so nothing is written twice.

This is also the honest answer to "which work is in the changelog": the whole accumulation, including
commits merged after the newest candidate. It is the same fact as "The cut absorbs everything after
the candidate", seen from the changelog side, and it is correct for this model rather than an
artifact.

If the changelog ever grows duplicate entries, this is the pair of settings to look at first: one of
the two runs is no longer passing its flag.

## The tag invariant

**Every tag in this repository is `vX.Y.Z` or a prerelease of exactly that shape, `vX.Y.Z-rc.N`.
Nothing else is ever created.**

Two settings in `releaserc.toml` enforce it:

- `tag_format = "v{version}"` — the version, prefixed, nothing else appended.
- `add_partial_tags = false` — the moving `v1` and `v1.0` aliases stay off. They were never
  actually created by the tool across four observed runs, and nothing adopts this repository by ref,
  so shipping them on trust would only add two tags that lie about the shape of the history.

A tag that is neither is a bug in `releaserc.toml`, not an accident to be cleaned up later.

## Before you merge

- [ ] The pull request title is a Conventional Commit: `fix:`, `feat:`, `perf:`, or a `chore:` /
      `docs:` / `ci:` / `refactor:` / `test:` prefix for work that changes nothing for a user.
- [ ] The change is user-facing, or deliberately not. `chore:` keeps the version still on purpose —
      that is the correct prefix for a dependency bump, a comment fix, or an unobservable change.
- [ ] A breaking change carries a `BREAKING CHANGE:` line in the body, and the title says what broke.
      This is what moves the major while the version is still zero (`major_on_zero = true`).
- [ ] `main` is green: CI passed on the merge, not on the branch from three commits ago.

## Cutting a release

1. Open the repository on GitHub, then **Actions** → **Release**.
2. Press **Run workflow**. The branch selector must be on `main`; the workflow refuses any other ref
   and says so, because candidates accumulate on `main` and nowhere else.
3. Read the run log. It ends in one of three lines:
   - `finalized a release: 1.1.0 as v1.1.0: <link>` — done, the release is public. The wording is
     historical and means "a full release was cut"; the number was computed from the last full
     release, not promoted from the candidate.
   - `no release was made` — behavior 1: there was no pending candidate and nothing releasable since
     the last full release. Nothing was cut.
   - anything else means the action failed; the tag was probably not written.
4. Open the tag `vX.Y.Z` on GitHub and read the release body and notes before announcing anything.
5. Announce, with the release link.

Between steps 3 and 5, nothing is public. That gap is the entire point of the model.

## Reverting

**Never delete a tag.** Not to undo a bad release, not to redo a number, not to "clean up" a
mistaken candidate.

A released tag is a promise that a version exists; deleting it makes every clone that already fetched
it fail, and it erases the only record of what shipped. Revert forward: open a pull request titled
`fix: <what was wrong>` describing the breakage, merge it, and let the next candidate carry the
correction. The version then reads `v1.1.1` after a `v1.1.0` that shipped a bug, which is the truth
— the bug shipped, and the fix shipped after it.

A mistaken *candidate* follows the same rule: leave `v1.1.0-rc.3` in place. It is a bookmark, not a
contract — the next cut will publish the whole accumulation since `v1.0.5` anyway, candidate or no
candidate. Nobody was told about it; deleting it only makes the history harder to read.

## Adopting this flow in another project

1. Start from `releaserc.toml` in this repository. Copy it, then delete what your project does not
   have and re-justify every comment you keep — a copied comment that no longer describes the line
   below it is worse than no comment.
2. Point `[semantic_release.branches.<name>]` at your default branch. The name is yours; `main` here.
   Keep `prerelease = false` and a `prerelease_token` you are willing to see in public tags.
3. Keep `add_partial_tags = false` unless something genuinely consumes the `v1` alias.
4. Keep the squash-merge settings (`parse_squash_commits = false`, `ignore_merge_commits = true`) if
   your repository squash-merges. They are not generic: with `parse_squash_commits = true`, GitHub
   puts the branch's whole commit list in the squash body and the releaser re-attributes already
   released fixes to whichever pull request merged last.
5. Copy the workflow. If the action gains an `--as-prerelease` passthrough in a future release, the RC
   run can go back onto the action and the direct invocation — with its own `setup-python` pin, its
   own dependency pin, its own committer step and its own tag-diffing report — can be deleted.
6. Set permissions deliberately: `contents: read` at workflow level, `contents: write` on the two
   release jobs. Add more only when you actually publish something that needs it.
7. Write the runbook for *your* maintainers, and spell out the two facts the numbers alone do not
   teach: that a cut recomputes from the last full release rather than promoting a candidate, and
   that it therefore absorbs every commit merged since the last full release — including commits
   merged after the newest candidate. The first person to dispatch a cut that ships more than the
   candidate they had in mind will otherwise assume the candidate tag was a snapshot.
