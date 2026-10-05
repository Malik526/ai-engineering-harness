# ADR 0005: Shared Fail-Closed Validation Confinement

Date: 2026-10-04
Status: Accepted

## Context

0.4 made browser/E2E results controller-owned, Bubblewrap-confined and immutable,
but normal tests/lint/type checks/builds still ran directly in the real worktree
with the controller environment and host network. Those results could authorize
a checkpoint, leaving a broader trust boundary than the browser gate they preceded.

## Decision

All deterministic checkpoint-capable validation uses a shared `SandboxPolicy`
and process lifecycle. Browser gates retain their 0.4 read-only host-root policy.
Normal validation uses a minimal root and a writable disposable materialization
of the exact synthetic Git tree, private scratch/cache/home/temp, explicit
read-only dependencies, `--clearenv`, and no network by default.

Prefer explicit argv while retaining legacy shell strings inside the same sandbox.
Derive PASS/FAIL/ERROR/SKIPPED from controller-observed behavior. Missing sandbox,
tool, mount/setup failure, malformed runtime policy and timeout fail ERROR; there
is no host fallback. The validation runner refuses to run without a controller
snapshot. Host execution is a separate, explicitly requested manual-completion
mode that never produces checkpoint evidence. The minimal root is sealed
read-only after setup, so only declared paths are writable. An explicit per-command `network: host` opt-in is visible in
evidence. Required non-PASS blocks checkpoint independently of reviewer PASS.

Persist immutable v2 evidence with run/cycle/source/config/command/policy/timing/
status identity and hashed raw logs. Anchor each attempt in `validation_history`;
verify history before review, resumed implementation and checkpoint. Revisions
always create a new source snapshot and normal/browser evidence before a fresh
review. Extend `autobuild evidence` to verify both classes.

## Consequences

Builds may write normally without mutating the source worktree, and setup output
can feed later commands/browser gates in the same attempt. Linux with usable
Bubblewrap namespaces becomes a hard prerequisite for checkpoint-capable normal
validation. Projects needing downloads must declare host networking. Existing
opaque `run` strings still work but argv is auditable and preferred.

This is defense in depth for trusted project validation, not a multi-tenant
security boundary. Kernel/runtime trust, explicit host network, dependency
integrity, secret content scanning, resource quotas, CI/distributed execution and
non-Linux backends remain outside 0.5. With all deterministic checkpoint gates
now confined, bounded rollover can be reconsidered for 0.6 without weakening
human approval, branch, stop, provider-fallback or merge/push boundaries.
