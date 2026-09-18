# Archived agent briefs and reports — `.superpowers/sdd/` (2026-07)

These are the task briefs and completion reports written by the agent team that
performed the original 2026-07 build of ResumeTailor. They were produced in the
repo-local `.superpowers/sdd/` working directory, of which only two files were
ever committed (`t2-llm-report.md`, `t6-tester-report.md`) — the rest sat
untracked next to them, and the directory itself was not gitignored.

Task 0.7 (defect D-62) settled that inconsistency: the markdown record is
preserved here, and `.superpowers/` is now ignored as the agent scratch
directory it is. The large raw artefacts left in that directory — multi-megabyte
`review-*.diff` and `review-*.txt` dumps — were deliberately not archived; they
are mechanical diffs of commits that remain in the git history.

The plans and specs that these briefs implement are archived alongside them, under
[`docs/archive/planning/superpowers/`](../planning/superpowers/). Task 1.6 completed the fold
that `PLAN.md` §3.3 called for; this directory is the reports half of that archive, landed early
because D-62 required a decision on the tracked files now. See
[`../planning/README.md`](../planning/README.md) for the rest.

These documents describe a build that has since diverged. They are history, not
specification — nothing here should be read as a current description of the
system.
