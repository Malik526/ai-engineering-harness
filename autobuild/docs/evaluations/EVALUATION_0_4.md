# Autobuild 0.4 Evaluation

Evaluation date: 2026-10-04 (America/New_York); live timestamps below use UTC,
which crossed into 2026-10-05. This is a measured 0.4 record, not an amendment to
the historical 0.3 provider/quota observations.

## Automated Verification

Combined regression command, from `autobuild/`:

```sh
.venv/bin/python -m pytest tests ../scripts/tests -q
bin/autobuild check
python3 ../scripts/setup/audit_instructions.py
git diff --check
```

Result: **368 passed**, including 58 new browser-contract/execution/review tests
and one new browser-fixture lifecycle test. All prior regression cases remain;
the existing browser-required test now asserts no checkpoint when coverage is
missing, intentionally superseding the inherited 0.3 manual-browser exception.
The suite includes schema/semantic config rejection, deterministic outcomes,
missing tools/sandbox, optional/disabled gates, timeouts/watchdog/interruption,
log bounds, artifact capture/link/traversal/secret-name/budget checks, worker
bootstrap isolation, fresh revision evidence, reviewer PASS barrier,
acknowledgement, explicit resume/tamper refusal and protected-ref invariants.

Native namespace and loopback server tests were run with explicitly approved
local permissions. Default managed execution denies sockets/namespaces, so
socket/native tests skip there; production gates fail ERROR rather than silently
running without confinement. PASS/FAIL/timeout server-cleanup tests, a real
namespace service test and read-only worktree/Git checks all passed in the
approved full run. Core schema/example check, installed policy audit and diff
check passed. No configured standalone type checker, linter or build exists;
regression tests and executable CLI/runtime checks are the applicable checks.

## Live Same-Provider Loop

Fixture: `.test-runtime/live-04-counter`, run `2026-10-04-V-1`.
Providers: Codex implementer and fresh Codex reviewers, CLI 0.160.0.
Window: `2026-10-05T02:43:35Z` -> `02:46:29Z`.

The explicitly approved fixture protocol deliberately created initial Counter
markup with no click handler. Normal validation prepared pinned Playwright
dependencies and checked HTML presence. Controller-owned real Chromium clicked
Increment: visible count stayed 0, assertion expected 1, exit 1 -> FAIL. A fresh
reviewer inspected the browser evidence and returned REVISE. The controller
resumed implementer `01a109f1-fd67-75b3-91c4-89070c6b6c76`; it wired the handler.
Normal validation and a new browser gate reran; real click produced 1, exit 0 ->
PASS. A second fresh reviewer returned PASS. Exactly one controller checkpoint
`a4cc414451d16138a71b885c5312d0e37c016a16` was made on the run branch, never merged/pushed.

Reviewers: `01a109f2-95b7-7493-8fce-30c4bc1f315c` (REVISE), then
`01a109f4-0d2b-70e1-9b85-869e5d9d28b3` (PASS).
Snapshot trees changed from `af4dc37774f50f81e955af67df272b8f4137d6a7` to
`fe38e77a3387451c0bee2e78d146203353c9d6da`.
Fixture main stayed `695134681878c094a2e12c63f9e8733eb8f3872e`.

## Live Cross-Provider Loop

Fixture: `.test-runtime/live-04-cross`, run `2026-10-04-V-1`.
Providers: Claude implementer (CLI 2.1.289), Codex reviewers (CLI 0.160.0).
Window: `2026-10-05T02:47:26Z` -> `02:49:18Z`.

The same real browser scenario completed FAIL -> REVISE -> resumed correction ->
fresh normal/browser PASS -> fresh reviewer PASS -> COMPLETED. Claude session
`082f658e-075e-4e29-af58-b45470453dff` was retained across implementation attempts.
Independent Codex reviewers were `01a109f5-d3a2-72a2-81be-704187fb7f10` and
`01a109f6-aedc-77c1-90bd-440710277eba`; statuses REVISE then PASS.
Snapshot trees: `0047ec6e3ab10b465c466d4bebcfb76bc8d88f5d` ->
`614c2223c45d2ecb6bd965a9df08763d1f90cba1`.
Single controller checkpoint: `378568de11537a3a5b2c9d40a0cf66ffb98bf88b`.
Fixture main stayed `b49b81f2a82b86dc878510ad4b9aaf3465d9e118`.

**No provider quota/authentication failure occurred in either 0.4 live run.**
The prior 0.3 Claude quota block is historical, not a current blocker. No provider
fallback was used. This evaluation does not establish unrestricted quotas or
prove the inverse provider assignment.

## Browser Artifacts And Cleanup

Both runs used Node 22.18.0, pinned Playwright 1.63.0 and the already installed
Chromium executable explicitly selected from `~/.cache/ms-playwright/chromium-1243`.
The controller started Python's HTTP server at private loopback port 38404;
no host service was reused. All four attempts preserved `counter.png`,
`trace.zip`, `report.json`, raw test/service logs and per-attempt hashed evidence.
The failure reports did not override actual command exit; reviewer inputs linked
the specific failed/passed attempt. Screenshot inspection confirmed the final
counter displayed 1. `autobuild evidence` verified both cross-provider manifests.

After the finalized isolated `python -I` worker bootstrap was added, a fresh
controller browser-only verification against the preserved fixed cross-provider
worktree again returned PASS/exit 0 with three artifacts; evidence was preserved
outside the repo at `/tmp/autobuild-04-final-browser-7z4m768k`. This did not alter
completed run history. Post-completion process inspection found zero remaining
fixture HTTP servers. Both completed fixture repositories and their numbered
failure/success evidence remain in the ignored owned runtime tree for inspection.

## Boundaries And Next Step

No harness commit, merge, push or rollover was performed. Fixture baseline and
controller checkpoint commits are isolated verification artifacts. Harness HEAD
remained `59e450e6d2042e65d62fb1fc5faa105f3ebba935` during validation.

Browser execution is Linux-only and requires usable Bubblewrap namespaces.
Read-only worktrees require explicit reporter/cache output paths. Project tests
remain trusted: host system/controller assets are readable, normal validation
is not sandboxed, resource quotas/content scanning are absent, and ignored
dependencies/build outputs are not represented by the Git snapshot. No cloud
browser, production endpoint, visual intelligence or distributed worker support.
0.5 should extend fail-closed confinement to ordinary validation before enlarging
autonomous scope with rollover.
