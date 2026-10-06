# ADR 0007: Controller-Owned Run Governance

Date: 2026-10-05
Status: Accepted

## Context

Through 0.6 a run was bounded only by review cycles, per-invocation timeouts
and one rollover. There was no total runtime or attempt budget, no way to stop
a run except Ctrl-C at its terminal, and notifications existed only as an
unused payload builder. Longer autonomous runs need a guarantee that the run
stops safely, for a recorded reason, however the agents behave.

## Decision

**Budgets are controller state, checked before every operation.** A
`Governor` checks the remote-stop channel and every configured budget before
each implementation, validation, browser and review operation. Counters are
derived from the run's own histories (attempts, validation and browser runs,
review cycles, rollovers) plus a `governance` record of controller sessions and
per-operation timing and usage, so they survive resume and cannot drift.
Runtime counts active controller time across sessions, not time blocked on a
human. Token usage is accounted only from provider-reported numbers; no cost is
estimated, and a usage budget is refused unless every configured provider
reports usage. Existing fields are reused: `max_review_cycles` and
`rollover.max_rollovers` remain the review and rollover budgets.

**Stops come from outside the model.** While an implementer or reviewer runs, a
watchdog thread polls the stop channel and the runtime deadline and terminates
the provider's process group. The first stop channel is a file in the run
directory written by `autobuild stop`, behind the existing provider-neutral
`StopController` interface.

**One canonical stop reason per run.** The state machine is unchanged: budget
stops end `HUMAN_BLOCKED`, stops end `STOPPED`, failures end `FAILED`.
`state.stop_reason` adds the canonical code, detail and, for budgets, the limit
and its use. Governance and rollover set codes explicitly; other outcomes are
derived from recorded failures, so a provider failure is never reported as
budget exhaustion.

**Raising a limit is an explicit, recorded human act.** Resume compares the
current config with the run's effective limits and applies a change only with
`--override-limits`, recording each change. An exhausted budget refuses to
resume until raised.

**Notifications are derived, best-effort side effects.** The payload is built
from the persisted state and controller artifacts after the state is written;
delivery errors are logged and never change the run.

## Alternatives Rejected

- Asking the agent to stop or respect a budget: models can ignore or misread
  instructions; the controller must hold the process.
- Wall-clock runtime since the run started: a run blocked overnight for a human
  would be "out of time" before doing any work.
- Estimating spend from token prices: providers differ and subscription usage
  has no reliable price; an invented number is worse than none.
- Silently honoring a raised limit found in the config on resume: it would make
  budgets ineffective against accidental or automated edits.
- New run states per stop cause: reasons belong in data; the state machine
  stays small and its transitions stay verified.

## Consequences

An autonomous run now either completes with verified evidence or stops
deterministically with its work preserved and the operator notified. Validation
and browser commands are not interrupted mid-command, token budgets can be
overshot by the operation in flight, and the only stop channel is local; a
phone-reachable channel is future work.
