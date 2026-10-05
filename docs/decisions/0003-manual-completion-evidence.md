# 0003 - Shared Manual Completion Evidence

**Status:** Accepted, 2026-10-04

## Context

ADR 0001 separates deterministic enforcement from semantic engineering decisions.
Manual work needs a completion check without acquiring Autobuild orchestration.
ADR 0002 provides owned adapter fragments and shared installation/audit wiring.

## Decision

Install one provider-neutral manual completion script and usage document through
the existing link manifest. Both owned adapter fragments instruct invocation
before normal completion. Use task-local JSON outside the repository for
repository-bound validation evidence and explicit documentation reconciliation.
Reuse the validation runner and command schema. Extract the existing secret-like
filename guard to a dependency-light shared module without changing its behavior.

No stop hook is added: the shared instruction works with both runtimes without
introducing provider-specific completion state. Invocation remains instructional;
Git/evidence/status checks are deterministic once invoked. Applicability, document
authority and conceptual correctness remain agent decisions under canonical policy.

## Consequences

No background service, branch/worktree creation, automatic commit, controller
state or repair loop. Autobuild environment markers return SKIP before any work;
its controller retains completion ownership. Full-content fingerprints reject
stale evidence, at the cost of rerunning checks after subsequent edits. JSON
reconciliation adds modest task-end work; future ergonomics should preserve the
same evidence contract rather than add another orchestrator. This does not prove
that the final reply includes the recommendation or that every applicable command
was selected. Filename detection remains conservative and is not a secret scanner.
