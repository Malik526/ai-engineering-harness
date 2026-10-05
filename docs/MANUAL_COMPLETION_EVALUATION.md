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
