# Project management rules

Adopted 2026-11-13 on takeover: fewer branches, faster merges, one written
record. The repo had 14 branches and 4 open PRs after three days; several
branches duplicated work already on main, and one closed PR's branch was still
open. These rules stop that drift.

## Branches

1. `main` is always deployable: backend tests pass, no known-broken export.
2. One active feature branch per workstream, branched from current `main`.
   Name: `feat|fix|docs/<short-kebab>`.
3. Small, focused PRs. Rebase onto `main` when behind by more than a few
   commits or on any conflict. Merge within days, not weeks.
4. Delete the branch immediately after merge. Enable GitHub's automatic
   branch deletion for the repository.
5. No new branch for: typo/doc fixes, single-file hygiene (commit direct to
   `main`), or a follow-up to a just-merged PR.
6. Stale-branch rule: a branch untouched for 7 days gets a keep-or-delete
   decision (rebase if kept). No branch outlives its PR: closing a PR
   unmerged means deleting its branch the same day, unless its unique work
   is explicitly recorded as kept in `PROJECT_LOG.md`.
7. Never run two parallel branches on the same file area (e.g. two
   MusicXML exporter branches). Sequence the work instead.

## Progress record

- Every merge, fix, and decision gets a dated entry in
  `docs/PROJECT_LOG.md`: what changed, exact test/benchmark result, and
  what remains open. No silent merges.
- Every work item has one GitHub issue; the PR that resolves it closes it.
- Do not claim a metric, test result, or visual acceptance without the
  recorded command, output, or inspected artifact behind it.

## Audio test data

- No audio files in the repository (see 2026-11-13 removal of two
  copyrighted MP3s). `scripts/engine_smoke.py` skips real-audio checks
  gracefully when no MP3 is present; synthetic mixes are the default.
- Real test audio lives outside the repo. Any file over a few MB, or any
  third-party recording, needs a license note in `docs/TEST_DATASETS.md`
  before it is referenced.
- `*.mp3`, `*.wav`, `*.flac` are git-ignored; the ignore rule is the
  backstop, review is the gate.
