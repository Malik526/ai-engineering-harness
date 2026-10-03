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
| `brief.md` | authoritative_evidence | planner | Human-approved brief, frozen at run start; hash in `state.json` |
| `state.json` | decision_record | controller | Current run state (`run-state.schema.json`) |
| `implementation/diff.patch` | authoritative_evidence | controller | `git diff` of the run branch against its parent |
| `implementation/changed-files.txt` | authoritative_evidence | controller | `git diff --name-status` against the parent |
| `implementation/validation.json` | authoritative_evidence | controller | Commands the controller re-ran, with exit codes (`validation.schema.json`) |
| `implementation/summary.md` | supplemental | implementer | Implementer's account of the change (`templates/implementation-summary.md`) |
| `browser/results.json` | authoritative_evidence | browser_tool | Browser assertions and console errors |
| `browser/screenshots/` | authoritative_evidence | browser_tool | Screenshots referenced by `results.json` |
| `review/review-NN.json` | decision_record | reviewer | Structured review result (`review.schema.json`) |
| `review/review-NN.md` | supplemental | reviewer | Reviewer's narrative for the same cycle (`templates/review.md`) |
| `logs/` | supplemental | controller | Raw agent and command logs |

`NN` is the two-digit review cycle (`review-01`, `review-02`, …).

## Rules

- **Validation is re-run, not reported.** `validation.json` counts as authoritative evidence only when `producer` is `controller`. Test results reported by the implementer are supplemental, and the notification marks them that way.
- **The brief is frozen.** The controller copies the approved brief into the run and records its SHA-256 as `brief_sha256`. The reviewer judges that copy. Edits to the roadmap brief during a run don't affect it.
- **Diffs come from git.** `diff.patch` and `changed-files.txt` are produced by the controller from the repository, never written by an agent.
- **Review status is structured.** Only `review-NN.json` `status` moves the state machine. PASS can't carry `blocker` or `major` findings, REVISE must carry at least one finding, and BLOCKED must give a `blocked_reason`. Every review must list `brief` and `git_diff` in `evidence_reviewed`.
- **Runs are local.** `runs/` is git-ignored in projects. Logs may contain environment details and shouldn't be committed.
