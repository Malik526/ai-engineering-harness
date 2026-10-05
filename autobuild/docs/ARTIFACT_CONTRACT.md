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
| `config.json` | authoritative_evidence | controller | Frozen execution configuration, checked on resume |
| `report.md` | supplemental | controller | Completion summary derived from the records above |
| `implementation/prompt.md` | authoritative_evidence | controller | Exact input the implementer received |
| `implementation/git.json` | authoritative_evidence | controller | Base/head commits, snapshot tree, git status, untracked files |
| `implementation/diff.patch` | authoritative_evidence | controller | Binary-safe diff of the worktree snapshot against the base commit |
| `implementation/changed-files.txt` | authoritative_evidence | controller | Name-status of the same snapshot |
| `implementation/result.json` | supplemental | implementer | How the provider process ended, plus the implementer's report (implementation-result.schema.json) |
| `implementation/summary.md` | supplemental | implementer | The implementer's report rendered as Markdown |
| `validation/results.json` | authoritative_evidence | controller | Commands the controller ran, with status and exit codes (validation.schema.json) |
| `implementation/cycle-NN/` | authoritative_evidence | controller | Per-attempt prompt, Git snapshot, diff and changed files; result/summary remain supplemental |
| `validation/cycle-NN/results.json` | authoritative_evidence | controller | Controller validation for each implementation attempt |
| `validation/cycle-NN/logs/` | authoritative_evidence | controller | stdout/stderr of each validation attempt |
| `browser/results.json` | authoritative_evidence | browser_tool | Browser assertions and console errors |
| `browser/screenshots/` | authoritative_evidence | browser_tool | Screenshots referenced by results.json |
| `review/review-NN.json` | decision_record | reviewer | Structured review result (review.schema.json) |
| `review/review-NN.md` | supplemental | reviewer | Reviewer's narrative for the same cycle |
| `review/review-NN-prompt.md` | authoritative_evidence | controller | Exact evidence-first reviewer input |
| `review/review-NN-result.json` | supplemental | controller | Process outcome and parsed report, including failed reviews |
| `logs/implementation-NN/` | supplemental | controller | Raw implementer process output for each attempt |
| `logs/review-NN/` | supplemental | controller | Raw reviewer process output for each review cycle |
| `logs/controller.log` | supplemental | controller | Controller step log |
| `logs/provider.log` | supplemental | controller | Raw provider stdout |
| `logs/provider.stderr.log` | supplemental | controller | Raw provider stderr |
| `guard/bin/git` | supplemental | controller | Per-run git guard placed first on the agent's PATH |

`NN` is the two-digit review cycle under `review/` and `logs/review-NN/`,
and the implementation attempt under `implementation/`, `validation/` and
`logs/implementation-NN/`. They may differ after resume or a failed review.
Unnumbered implementation and validation results are latest aliases;
numbered artifacts are preserved across revisions and explicit resume.
Git snapshot trees and cumulative base-relative diffs reconstruct each attempt
without intermediate revision commits. `checks/` holds post-validation/review
comparison snapshots; `.controller.lock` prevents concurrent controllers.

## Rules

- **Validation is re-run, not reported.** `validation/results.json` counts as authoritative evidence only when `producer` is `controller`. The implementer's `tests_reported` in `result.json` is supplemental, and the notification marks it that way.
- **The brief is frozen.** The controller copies the approved brief into the run and records its SHA-256 as `brief_sha256`. The reviewer judges that copy. Edits to the roadmap brief during a run don't affect it.
- **Diffs come from git.** `diff.patch`, `changed-files.txt` and `git.json` are produced by the controller from a snapshot of the worktree (taken through a temporary index, before validation runs), never written by an agent. The checkpoint commit is built from exactly that snapshot's tree.
- **The prompt is recorded.** `implementation/prompt.md` is the exact input the implementer received, so a reviewer can tell an implementation error from an instruction error.
- **Review status is structured.** Only a schema-valid `review-NN.json` moves the state machine. PASS cannot carry blocker/major findings; REVISE requires findings; BLOCK requires `blocked_reason`. Legacy BLOCKED is accepted and normalized to BLOCK. The runner requires brief, git_diff, changed_files and validation_output evidence, matching run/implementation/cycle and unique finding IDs. Actual provider/session/time come from the controller, not agent claims.
- **State retains history.** `review_cycle`, `agent_sessions`, `review_history`, `revision_history`, `final_review_status` and `protected_refs` record observed identities, outcomes, snapshot trees, artifact pointers and resumption IDs. Invalid writes are rejected transactionally. No final checkpoint occurs before PASS.
- **Runs are local.** `runs/` is git-ignored in projects. Logs may contain environment details and shouldn't be committed.
