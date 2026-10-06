# Autobuild 0.7 Evaluation

Evaluation date: 2026-10-05 (America/New_York; run timestamps are UTC, early
2026-10-06). This record evaluates bounded autonomous-run governance:
controller-owned budgets, canonical stop reasons, remote stop, notifications
and governed resume. Providers: Claude Code 2.1.290, Codex CLI 0.160.0.

## Automated Verification

```sh
cd autobuild
.venv/bin/python -m pytest tests ../scripts/tests -q
bin/autobuild check
python3 ../scripts/setup/audit_instructions.py
git diff --check
```

Result: **466 passed** (438 before 0.7, 28 new), plus the core schema/example
check, instruction audit and whitespace check. The 0.3–0.6 suites run unchanged
except where 0.7 deliberately changed a contract: a raised review budget now
needs `--override-limits`, and notifications no longer fire on the transient
`PASSED` state.

New coverage (`tests/test_governance.py`), all with fake providers:

| Brief item | Tests |
| --- | --- |
| Runtime budget | stop at the next boundary; a running provider terminated by the watchdog (PID verified dead, partial work kept) |
| Review / revision / validation / usage budgets | canonical reason with limit and use for each; token budget from provider-reported usage |
| Rollover budget | `rollover_budget_exhausted` vs `provider_failure` for an unavailable replacement; a takeover consumes the revision budget and nothing resets |
| Unknown provider failure | fails closed (`provider_failure`, no rollover) |
| Remote stop | before the provider starts (no session created, request acknowledged); during execution (provider terminated, partial work, prompt and state kept, `stopped` notification with resume instruction) |
| Resume | after remote stop (history and accounting continue, two segments); pending stop blocks resume until `--clear`; budget stop refuses until raised and `--override-limits`; a lowered limit is also an explicit override |
| Notifications | structured final notification for completed, human action, failed and budget stop; rollover notification names the incoming implementer; delivery failure never affects the run; email over a local SMTP server |
| Configuration | rollover with zero revision attempts, unimplemented stop provider, email without settings, runtime 0, usage budget with a provider that reports no usage |

Mutation checks: making the operation gate a no-op fails eight tests; removing
the watchdog's termination makes the mid-operation stop test fail after the
provider runs to its own timeout.

## Live Verification

All fixtures are disposable under the ignored `.test-runtime/`, have no remote,
used file notifications and the file stop provider, and kept `main` at its base.
No validation, browser or provider process remained after any run.

### Remote stop during a real provider run

`live-07-remote-stop`, Codex implementer. A driver waited for `IMPLEMENTING`,
let Codex work for six seconds, recorded its two processes (cwd = the run
worktree) and ran `autobuild stop RUN --reason "live 0.7 remote stop
verification"` at 01:08:25.45Z. The controller exited at 01:08:27.43Z (within
one poll interval); both Codex processes were gone. The run ended `STOPPED`,
`stop_reason: remote_stop` with the operator and reason; the request was
acknowledged; the attempt was recorded `interrupted`; branch and worktree were
preserved; no checkpoint; a `stopped` notification was written.

### Runtime budget

- `live-07-runtime-budget` (Claude/Claude, 1 minute): the full two-cycle
  browser run completed in 58.8 s of active time. That is just inside the
  budget, so it completed and checkpointed normally, and the accounting is
  shown to be exact.
- `live-07-runtime-budget-codex` (Codex/Codex, 1 minute):
  - Cycle 1: implementation, validation PASS, browser FAIL, Codex reviewer
    REVISE (49 s).
  - The watchdog terminated the resumed Codex revision at 61.7 s.
  - The run ended `HUMAN_BLOCKED`, `runtime_budget_exhausted` (limit 1, used
    1.03), with the uncommitted `index.html` preserved and no checkpoint.
  - A `budget_exhausted` notification carried the exact resume command.

### Governed resume of the budget stop

On the same run:
1. `autobuild resume` refused while the budget was exhausted.
2. After the limit was raised to 10 in the working copy, it refused without
   `--override-limits`.
3. With the flag, the override was recorded (`limits.max_runtime_minutes 1 ->
   10`).

The interrupted Codex session itself resumed; fresh validation and browser PASS
followed, and a fresh Codex reviewer returned PASS. Checkpoint `c27cc9265fbc`.
Runtime accumulated across both controller sessions (61.7 s + 67.8 s = 2.16 of
10 min), attempts and review cycles continued (3 attempts, 2 cycles), and
notifications read `budget_exhausted` then `completed`.

During this check the operator step was first done by committing the raised
limit to the fixture's `main`. Resume then refused because a protected ref had
moved since the run started. That is correct behavior: raise limits in the
working copy, not on a protected branch, while a run is preserved. The
disposable fixture's `main` was reset to its recorded ref before the real
resume.

### Rollover with every budget configured

`live-07-rollover-budgets` (browser fixture, Codex implementer, Claude
reviewer and replacement, induced session loss on resume as in 0.6). Budgets:
runtime 30 min, revisions 3, validation 5, browser 5, tokens 5M.

- Codex initial, then Claude REVISE.
- The Codex resume failed `session_unavailable`; Claude took over by rollover.
- Fresh validation, browser and Claude reviewer PASS; checkpoint `5e9043aa726c`.

Final counters: revisions 2/3 (resume + takeover), rollovers 1/1, review
cycles 2/3, validation 2/5, browser 2/5, tokens 687,475/5,000,000 (the failed
resume reported no usage and is listed as such), runtime 1.51/30 min.
Notifications: `rollover` then `completed`; all manifests and the handoff verify.

### Completion notification

`live-07-complete` (Claude/Claude, runtime 30 min, tokens 3M): completed with
checkpoint `0e928c1870bc`. `notifications/01-completed.txt` is the
phone-readable message: changed file, providers and counts, validation,
browser, review, branch and commit, protected branches unchanged.

### Found live and fixed

- The rollover notification named the failed implementer, because it was sent
  before the replacement's session existed. It now names the incoming one
  (unit-tested).
- Resume listed an exhausted run-wide budget twice; deduplicated.
- Stopped and blocked reports now show the preserved work from a controller
  snapshot, report operations without usage, and give minutes to two decimals.

## Safety Regression

Isolated worktrees, protected-branch checks, confined validation, immutable
browser evidence, fresh reviewers, fail-closed Bubblewrap and bounded rollover
are unchanged and their suites pass. No governed stop checkpointed, merged or
pushed. Notification delivery runs after the state is persisted, and its
failures are recorded separately.

## Limitations

- Validation and browser commands are not interrupted mid-command; a stop or
  runtime limit takes effect at the next boundary, bounded by their timeouts.
- Token budgets use provider-reported usage after each operation; the operation
  in flight can overshoot, and an operation killed before reporting counts as
  unreported. No spend in currency is enforced.
- The only stop channel is a local file (`autobuild stop`); GitHub/Supabase
  channels are not implemented.
- Email delivery was verified against a local SMTP server, not a real mail
  provider.
- Runtime counts active controller time; a controller killed with SIGKILL
  keeps only the time recorded up to its last completed operation.
