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

## Addendum (2026-11-25): one final validation run, blocked runs and evidence reuse

**Context.** Manual sessions ran their own full test, lint and build commands, then
ran them again through `--run-validation`. `VERIFICATION.md` and the adapter each
asked for a final run without saying one covered the other. The script also ran
commands when completion was already blocked (a stale reconciliation, unacknowledged
files), and `--run-validation` always reran, even for unchanged passing evidence.

**Decision.**

- In manual development the check's `--run-validation` run is the final run of the
  applicable suites. Agents run focused checks while implementing. Stated in the
  README, both adapter fragments and `VERIFICATION.md`.
- Every check that doesn't depend on test results now runs first. If any fails,
  validation is `blocked` and no command runs.
- `--run-validation` reuses stored evidence when the root, fingerprint and exact
  command list match, every required command passed, the environment digest matches
  and the run is at most an hour old. Otherwise it runs. `--fresh-validation` forces a run.
- The result reports `validation_run` (`executed`, `reused`, `blocked`,
  `not_requested`, `not_applicable`) and `validation_run_reason`. Existing fields
  and the commit-recommendation flag are unchanged.

**Consequences.** One full run per task in the normal case, plus one more whenever
code or documentation changes after it (unchanged: the fingerprint still covers
every changed file). Results the agent reports itself are still never evidence.
The environment digest hashes variable values one way and skips `PWD`, `OLDPWD`,
`SHLVL` and `_`. Changes outside Git and the environment, such as dependency
installs into ignored directories or tool upgrades, aren't detected; the one-hour
window bounds that risk and `--fresh-validation` covers it explicitly. Choosing
proportional commands remains the agent's documented decision in
`validation_scope`. Autobuild's controller validation is unchanged and the
Autobuild markers still return SKIP before any of this.
