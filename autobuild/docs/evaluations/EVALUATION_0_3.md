# Autobuild 0.3 Evaluation

**Date:** 2026-10-04 (America/New_York; live artifact timestamps use UTC)
**Status:** Implementation verified; live cross-provider completion remains quota-blocked.

## Automated Coverage

`autobuild/.venv/bin/python -m pytest autobuild/tests scripts/tests -q`
passes 308 combined harness/Autobuild regression tests. Fake-provider review
tests cover all 15 requested categories: first PASS, one/multiple revisions,
budget exhaustion, BLOCK, fresh identities across cycles/roles, cross-provider
assignments, validation on every correction, no review after validation failure,
read-only adapter/hook/Git behavior and mutation detection, artifact retention,
unavailable reviewer refusal, preserved resume and unchanged protected branches.

Additional negative cases cover invalid/crashed reviews, invalid final-budget
reviews, reused implementer/reviewer IDs, resumed-provider identity mismatch,
validation content mutation, frozen brief/config/ref/branch/secret/artifact/lock
tampering, non-recoverable/terminal resume refusal, and human budget increases.
Codex schema projection is tested separately from full local contract validation.
Existing GREEN/YELLOW/RED, secret-like filename, agent-commit/push and protected
ref tests remain in force. Core provider-name and doc-contract tests pass.

Other checks: `autobuild/bin/autobuild check`,
`python3 scripts/setup/audit_instructions.py`, and `git diff --check` pass.
No configured type checker, formatter or application build exists for this
Python controller change. Live CLI execution supplies runtime verification.

## Live Same-Provider Revision

Owned fixture: `autobuild/.test-runtime/live-03-codex-revision`.
Codex CLI 0.160.0, implementer and reviewer both configured as Codex.
The fixture's initial-only implementer protocol deliberately writes a wrong
line; controller validation checks file existence, leaving content correctness
to independent review against the unchanged approved brief. Revisions must fix
the exact content. This protocol is confined to the ignored disposable fixture.

Run: `2026-10-04-V-1-2`, branch `agent/V-1-autobuild-verification-file-2`.

- Implementer `01a109d2-a14f-7f82-ac4d-24bf3579969d` produced the deliberate defect.
- Controller validation passed; fresh reviewer
  `01a109d3-35c3-7fc2-89b5-3367a926e82c` returned REVISE.
- The same implementer session resumed and corrected the file. Validation reran.
- Fresh reviewer `01a109d4-08de-7340-bec8-43c4583ae0ff` returned PASS.
- Controller checkpoint `a52f2e0372d29286a013e2aaa7936edcdaccf335` was created
  only on the run branch. State is COMPLETED, two reviews/two validation attempts.
- Fixture main remained `621a1c31c82547296276ed467425b349f2c22073`.
  Final content is the approved line `Autobuild 0.2 verification` (the existing
  fixture brief's literal content, not the harness phase number).

Numbered prompts, diffs, snapshot trees, reports, validation logs and review
decisions preserve both versions. No intermediate revision commit, merge or push.

## Live Explicit Resume And Compatibility Findings

The fixture's original run `2026-10-04-V-1` exposed two provider-contract issues:
the API rejected full review-schema `allOf`, then a structural-only projection
allowed a date-only `reviewed_at`, which the full local schema correctly refused.
The adapter now projects supported API keywords, keeps supported value constraints,
requires nullable optional fields, and validates the parsed result against the
full original contract. These failed attempts were not silently accepted/reset.

Explicit `autobuild resume .autobuild/runs/2026-10-04-V-1` retained the original
run/worktree/implementer and failed-review history. The final fresh review at
cycle three passed; checkpoint `b37563a7fedf` was isolated to its run branch.
This supersedes those initial compatibility failures, not their historical logs.

## Live Cross-Provider Attempt

Owned fixture: `autobuild/.test-runtime/live-03-cross`, Claude implementer and
Codex reviewer. Claude Code 2.1.289 passed its local health check but returned
HTTP 429/session limit before implementing: "resets 10:40pm (America/New_York)".
Run `2026-10-04-V-1` stopped FAILED/provider_failed at review cycle zero. No
reviewer, fallback, checkpoint, merge or push ran. Fixture main remained
`bb2d25057bfb9b954e59f4187b6f1c0faabc5750`; its empty worktree/session/logs remain.

This is **not a passing live cross-provider result**. Configured cross-provider
orchestration passes fake-provider tests and both adapter commands are covered,
but Claude reviewer/resume execution also remains unverified live in this task.
After quota resets, a human can explicitly resume this fixture from its root:

```sh
/home/malik/ai-engineering-harness/autobuild/bin/autobuild resume .autobuild/runs/2026-10-04-V-1
```

The brief's complete live-verification requirement is pending that result.

## Remaining Boundaries And 0.4

No browser certification, roadmap rollover, multi-item run, notifications,
remote control, consensus, provider fallback or deployment is implemented.
Browser-required runs stay HUMAN_BLOCKED even after explicit resume. Legacy 0.2
runs cannot resume safely; unrelated protected-ref movement also requires a new
run. Hard crashes may leave a lock needing human investigation. Filename checks
are not content secret scanning; ignored outputs/process side effects remain
outside Git snapshots. Claude implementer OS confinement retains the 0.2 gap.

Recommended 0.4 scope: controller-owned browser/E2E evidence using existing
tools, per-attempt assertions/screenshots/console errors, deterministic browser
gates integrated into review prompts, and explicit resumption after verified
browser prerequisites. Keep roadmap rollover deferred to 0.5.
