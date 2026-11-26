# Manual Completion Evaluation

## 2026-10-04 - Shared Evidence Check

Architecture: ADR 0003. Usage: `scripts/manual/README.md`.
This dated result adds evidence without rewriting prior runtime evaluations.

Automated fixture coverage:

| Case | Result |
| --- | --- |
| Code change with successful validation | PASS with fresh repository-bound results |
| Required validation skipped/failed | NEEDS_ATTENTION |
| Documentation reconciliation omitted | NEEDS_ATTENTION |
| No documentation update appropriate | PASS with explicit reasons |
| Suspicious secret-like file | NEEDS_ATTENTION; validation not launched |
| No-change / analysis-only task | PASS; no commit recommendation |
| Uncommitted manual changes | Recommendation flag true; explicit commit request suppresses flag |
| Claude adapter | Canonical reminder and installed adapter verified |
| Codex adapter | Same shared reminder and installed adapter verified |
| Autobuild active | Immediate SKIP outside even a Git repository |
| Content/configuration changed after validation | Stale evidence rejected |
| Claimed documentation update without changed path | NEEDS_ATTENTION |
| Missing runtime applicability decision | NEEDS_ATTENTION |
| Unsafe validation command/log specification | Existing command schema rejects it |
| Unacknowledged/staged file | Status captured; acknowledgement required |
| Unborn repository | Snapshot supported |
| Merge conflict / in-progress Git operation | NEEDS_ATTENTION |

Verification:

- `autobuild/.venv/bin/python -m pytest scripts/tests autobuild/tests -q`:
  **265 passed**, including 20 manual completion fixtures and the existing
  Autobuild/controller/runtime regression coverage.
- `python3 scripts/setup/audit_instructions.py`: **PASS**, both installed
  adapters and guards match canonical definitions; policy coverage passes.
- `git diff --check`: **PASS**.
- The implementation task used the same script with task-local reconciliation
  and fresh validation evidence before reporting completion.

No live provider session is needed to validate adapter installation, parsing or
shared script behavior; those are deterministic fixtures. This evaluation does
not claim a measured invocation rate in live Claude/Codex sessions. No new vendor
hook or API was introduced. Existing runtime live evaluations remain historical.

Remaining limits: adapter-driven invocation and final message formatting are
instructional; evidence is not tamper-resistant; applicability/document authority
are semantic assertions; ignored files and credentials in ordinary filenames
need existing project content scanners. Full repository fingerprints include
baseline work, so later unrelated edits invalidate evidence. Filename checks are
conservative, including sample environment filenames. Commands use the existing
shell runner and should only be selected when safe. This layer creates no
validation configuration of its own: command lists reuse existing project commands
or configured Autobuild specs.

Next improvement: simplify task-local reconciliation authoring while preserving
explicit applicability decisions and the existing evidence contract.

## 2026-11-25 - Blocked Runs And Evidence Reuse

Architecture: ADR 0003 addendum (2026-11-25). Usage: `scripts/manual/README.md`.

New automated fixture coverage (14 cases):

| Case | Result |
| --- | --- |
| Stale reconciliation fingerprint with `--run-validation` | `blocked`; no command runs, no evidence written |
| Unacknowledged changed file | `blocked`; no command runs |
| In-progress Git operation and secret-like file | `blocked`; no command runs |
| Second `--run-validation`, nothing changed | `reused`; same evidence, command ran once, PASS |
| Stored run failed | `executed` again |
| Repository changed | `executed` again; PASS with new evidence |
| Command list changed | `executed` again |
| Environment variable added | `executed` again |
| Only `PWD`/`OLDPWD` differ | `reused` |
| Evidence older than the reuse window | `executed` again |
| Evidence without reuse metadata (written before this change) | `executed` again |
| `--fresh-validation` (function and CLI) | always `executed` |
| Check without `--run-validation` | `not_requested`; reads evidence only; `not_applicable` without commands |

Verification:

- `autobuild/.venv/bin/python -m pytest scripts/tests autobuild/tests -q`:
  **489 passed**, including 34 manual completion fixtures (20 existing, 14 new)
  and the unchanged Autobuild/controller/runtime coverage.
- `python3 scripts/setup/install.py --apply` updated both installed adapters;
  `python3 scripts/setup/audit_instructions.py`: **PASS**.
- The implementation task used the updated check for its own completion.

Remaining limits: agents still choose the commands (recorded in
`validation_scope`) and invocation stays instructional. Reuse can't see changes
outside Git and the environment (dependency installs into ignored directories,
tool upgrades); the one-hour window and `--fresh-validation` cover them.
