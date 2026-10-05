# Autobuild 0.5 Evaluation

Evaluation date: 2026-10-05 (America/New_York). Live run timestamps use UTC and
began late on October 4 local time. This record evaluates shared
fail-closed confinement for normal validation; it does not introduce rollover.

## Automated Verification

Commands:

```sh
cd autobuild
.venv/bin/python -m pytest tests ../scripts/tests -q
bin/autobuild check
python3 ../scripts/setup/audit_instructions.py
git diff --check
```

The regression suite includes native Bubblewrap tests for PASS/FAIL/ERROR,
timeouts, missing executable/sandbox/setup, no host fallback, arbitrary host
read/write denial, source-worktree/ref protection, default network denial and
explicit host opt-in, environment filtering/value omission, writable build/
home/cache/temp/scratch, Python/Node/static checks, detached children on success
and failure, interruption cleanup, evidence hashes/source identity/tamper,
revision freshness, resume and reviewer-PASS checkpoint barriers. Browser and
0.3 review/resume regressions remain in the same suite.

Result: **384 passed**, 16 more than 0.4's 368 combined tests. Core schema/example
checks, installed instruction audit, compileall and `git diff --check` also pass.
Native namespace tests were run with explicit permission; production remains
fail-closed when namespace creation is denied.

## Live Positive: Codex/Codex

Fixture `.test-runtime/live-05-positive`, run `2026-10-04-V-1`, window
`2026-10-05T03:52:43Z` to `03:53:52Z`. Codex CLI 0.160.0 implemented the
approved file; a fresh Codex session reviewed it. Confined `content-check` ran
with network none and returned PASS on snapshot
`919a65d0e661b8f331be50f5c1354ba86470b5e6`. Reviewer PASS produced one
controller checkpoint `bf20f191ccc1b11294dafd31b77f23688ba0e16a` on the run
branch. Fixture main remained `e7c7324c241c02228af9807cba2876dfc2bbe29a`.
Implementer session `01a10a31-4492-7d21-9336-d245f26eff65` and reviewer
`01a10a31-d1fa-7882-ba2a-47d8819ac032` were distinct.

## Live Revision: Claude/Codex

Fixture `.test-runtime/live-05-revision-2`, run `2026-10-04-V-1`, window
`2026-10-05T03:58:15Z` to `04:00:27Z`. Claude Code 2.1.289 followed a controlled
two-attempt protocol: it created a working browser counter plus an intentionally
incorrect marker. Normal setup PASS used explicit host network, HTML PASS and
marker FAIL used network none; aggregate normal validation was non-PASS on tree
`a63d76920e80c0ba915e1a78058171c33f333000`. Real Playwright browser evidence
PASS showed count 1 after click. Fresh Codex reviewer
`01a10a36-ea0d-7863-960d-4218a7055762` returned REVISE.

The same Claude session `2c1c85d2-6f91-4ceb-9f24-505cc1a63f8b` resumed and
changed only the marker. The controller captured new tree
`ed99f393882225fabb78e6a4800ffd013c19a231`, reran dependency/HTML/marker normal
validation to PASS, reran Playwright to PASS with three fresh artifacts, and
started reviewer `01a10a37-ba2b-70a2-82a7-59d56f19ab25`, which returned PASS.
Checkpoint `9dff29ce24eab2acbc036ab305ec00801522ff8d` exists only on the run branch;
fixture main stayed `8c16d43ae721705a3e54bb3893ca6e14d97a8584`.

The first cross-provider fixture `.test-runtime/live-05-revision` correctly
failed closed with no checkpoint when npm's internal wrapper was selected ahead
of its Node installation bin, causing setup FAIL/browser ERROR. That live finding
changed sandbox PATH construction to preserve the configured executable's parent
before resolving symlinks and added `npm --version` coverage. The fresh replacement
run above proves the fix; the blocked artifact remains historical, not presented
as a successful revision.

## Adversarial And Integrity Results

An explicit native adversarial fixture subset passed **5/5** after the PATH fix.
Commands could not read an arbitrary host secret, write an outside file or real
worktree, reach the fixture Git metadata/update main, inherit an undeclared AWS
secret, or reach loopback under network none. Explicit host networking connected
and was visible in evidence. Detached children did not survive success or failure.
The broader combined suite also covers timeout and interruption cleanup.

`autobuild evidence` verified all normal and browser manifests for both completed
runs, including both historical revision attempts. The browser screenshot shows
visible count 1. Both fixtures have no remote; their main refs equal their base
commits. Process inspection found no fixture HTTP server, provider or validation
child. Harness HEAD and main remained
`a01f8bc520db8cbd9551a942230eeb00c8dc5dc1`. No provider substitution occurred.

## Takeover Verification And Hardening (2026-10-05)

Codex hit its usage limit after the manual completion gate returned PASS, before
writing its final report. Claude Code took over from the uncommitted worktree,
re-ran the suite (384 passed), re-verified every live manifest above with
`autobuild evidence`, and confirmed the fixture refs and absence of leftover
processes. Review of the diff found no broken area. It did find two weaker points,
now hardened:

- **Implicit host path.** `run_validation` ran on the host whenever no snapshot
  tree was passed. The runner always passes one, but an omitted argument would
  have silently run unsandboxed. Host execution now requires an explicit
  `manual_host=True` (manual completion only); otherwise the call raises.
- **Writable ephemeral root.** The first controller-level adversarial run
  (`.test-runtime/live-05-adversarial`) showed a write to `$HOME/…` succeeding
  *inside* the sandbox: the minimal root was a writable tmpfs. Nothing reached
  the host, but writes outside the approved paths were possible. The root is now
  remounted read-only after setup, with `/tmp` as its own tmpfs. That run's FAIL
  is kept as historical evidence of the finding.

Five native tests were added: credential directories and harness `.git`
invisible, no host fallback without a snapshot, malformed runtime network policy
→ ERROR without execution, detached child reaped after timeout, and read-only
root. A mutation check confirmed that the read-only-root test fails without the
fix. Result: **389 passed** (21 more than 0.4).

### Live Adversarial Run (controller-level)

Fixture `.test-runtime/live-05-adversarial-2`, run `2026-10-05-V-1`, through
`autobuild run` with the final code. Codex was quota-blocked until 04:25 local,
so Claude Code 2.1.289 was configured explicitly for implementer and reviewer.
This was a declared pairing, not a fallback. The fixture's required validation
commands were hostile probes, each exiting 0 only if its escape was denied. The
controller ran with fake `AWS_SECRET_ACCESS_KEY`/`GITHUB_TOKEN`/canary values
in its environment and a host listener on `127.0.0.1:38499`.

| Probe | Result |
| --- | --- |
| Read `~/.ssh`, `~/.codex/auth.json`, `~/.claude`, `~/.agents`, a canary in the fixture's `.git`, fixture config, harness `.git` | PASS — none visible |
| Write fixture root, worktrees dir, `$HOME`, real worktree (legacy `run` shell string) | PASS — "Directory nonexistent" / "Read-only file system"; no host file created |
| Move fixture `main` / create a ref | PASS — repository not reachable; refs unchanged |
| Connect to host loopback listener and `1.1.1.1:443`, resolve DNS (network none) | PASS — listener logged no connection |
| Inherit controller secrets / SSH agent; explicit setting present | PASS — none inherited; canary values absent from every run file |
| Leave detached `sleep` children | PASS — none survived |
| Write snapshot copy, build dir, HOME, cache, scratch, temp | PASS — real worktree file unchanged |

Normal validation aggregated PASS on snapshot
`1a7879d1038ddc331a4cd0c95c961af16a2f7386`, and its manifest verifies. The run
then stopped `FAILED (reviewer_failed)` with no checkpoint. The Claude reviewer
cannot run at all (see Limitations below), so this run proves confinement, not
the PASS → checkpoint path. Codex/Codex and Claude/Codex above prove that path.
Fixture `main` stayed `5dd01165e870`. No validation temp root, sandbox, worker or
probe child remained.

## Boundaries And 0.6 Recommendation

No harness commit, merge, push, deployment or roadmap rollover is part of 0.5.
Linux/Bubblewrap and configured runtime binaries remain prerequisites. The
sandbox does not add seccomp, content scanning, dependency attestation, CPU/memory
quotas, CI/distributed workers or cross-platform backends; `network: host` is an
explicit broad opt-in. Explicit `env` values are non-secret literals, and there
is no secret-injection mechanism. A single validation output file is capped at
64 MiB.

Newly found, outside 0.5's scope: Claude Code 2.1.289 rejects the review
schema's top-level `allOf`, so a Claude reviewer always fails `reviewer_failed`
(see `PROVIDERS.md`). This turns 0.3's "Claude reviewer unverified live" into a
known defect. Codex remains the only working reviewer.

The live proof supports 0.6 introducing bounded single-project rollover:
select only the next already-approved GREEN brief, retain per-item stop/spend/
review limits, and never merge/push/deploy. Confinement was the prerequisite;
rollover is now justifiable only with equally explicit queue and human-control
boundaries.
