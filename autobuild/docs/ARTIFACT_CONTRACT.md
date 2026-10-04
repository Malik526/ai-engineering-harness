# Artifact Contract

Every run writes to `<project>/<paths.runs_directory>/<run-id>/`. Run ids are
`<YYYY-MM-DD>-<implementation id>[-<n>]`. The table below is defined in
`autobuild/artifacts.py`, and a test keeps the two in agreement.

## Authority

- **Authoritative evidence.** The reviewer may rely on it. It's produced by the controller, by git, or by the browser tool, or it's the human-approved brief.
- **Decision record.** Drives the state machine.
- **Supplemental.** Agent narrative. The reviewer reads it last and never accepts a claim from it without evidence.

The reviewer gets the evidence first. The implementer doesn't get to frame
the review.

## Run Directory

| Path | Authority | Producer | Contents |
| --- | --- | --- | --- |
| `brief.md` | authoritative_evidence | planner | Human-approved brief, frozen at run start; hash in state.json |
| `state.json` | decision_record | controller | Current run state (run-state.schema.json) |
| `report.md` | supplemental | controller | Completion summary derived from the records above |
| `implementation/prompt.md` | authoritative_evidence | controller | Exact input the implementer received |
| `implementation/git.json` | authoritative_evidence | controller | Base/head commits, snapshot tree, git status, untracked files |
| `implementation/diff.patch` | authoritative_evidence | controller | Binary-safe diff of the worktree snapshot against the base commit |
| `implementation/changed-files.txt` | authoritative_evidence | controller | Name-status of the same snapshot |
| `implementation/result.json` | supplemental | implementer | How the provider process ended, plus the implementer's report (implementation-result.schema.json) |
| `implementation/summary.md` | supplemental | implementer | The implementer's report rendered as Markdown |
| `validation/results.json` | authoritative_evidence | controller | Commands the controller ran, with status and exit codes (validation.schema.json) |
| `validation/logs/` | authoritative_evidence | controller | stdout/stderr of every validation command |
| `browser/results.json` | authoritative_evidence | browser_tool | Browser assertions and console errors |
| `browser/screenshots/` | authoritative_evidence | browser_tool | Screenshots referenced by results.json |
| `review/review-NN.json` | decision_record | reviewer | Structured review result (review.schema.json) |
| `review/review-NN.md` | supplemental | reviewer | Reviewer's narrative for the same cycle |
| `logs/controller.log` | supplemental | controller | Controller step log |
| `logs/provider.log` | supplemental | controller | Raw provider stdout |
| `logs/provider.stderr.log` | supplemental | controller | Raw provider stderr |
| `guard/bin/git` | supplemental | controller | Per-run git guard placed first on the agent's PATH |

`NN` is the two-digit review cycle (`review-01`, `review-02`, …).

## Rules

- **Validation is re-run, not reported.** `validation/results.json` counts as authoritative evidence only when `producer` is `controller`. The implementer's `tests_reported` in `result.json` is supplemental, and the notification marks it that way.
- **The brief is frozen.** The controller copies the approved brief into the run and records its SHA-256 as `brief_sha256`. The reviewer judges that copy. Edits to the roadmap brief during a run don't affect it.
- **Diffs come from git.** `diff.patch`, `changed-files.txt` and `git.json` are produced by the controller from a snapshot of the worktree (taken through a temporary index, before validation runs), never written by an agent. The checkpoint commit is built from exactly that snapshot's tree.
- **The prompt is recorded.** `implementation/prompt.md` is the exact input the implementer received, so a reviewer can tell an implementation error from an instruction error.
- **Review status is structured.** Only `review-NN.json` `status` moves the state machine. PASS can't carry `blocker` or `major` findings, REVISE must carry at least one finding, and BLOCKED must give a `blocked_reason`. Every review must list `brief` and `git_diff` in `evidence_reviewed`.
- **Runs are local.** `runs/` is git-ignored in projects. Logs may contain environment details and shouldn't be committed.
