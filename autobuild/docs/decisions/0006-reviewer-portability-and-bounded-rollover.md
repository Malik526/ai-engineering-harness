# ADR 0006: Reviewer Portability And Bounded Provider Rollover

Date: 2026-10-05
Status: Accepted

## Context

0.5 found that Claude Code could not act as reviewer: its `--json-schema`
becomes a tool `input_schema`, and the API rejects the review contract's
top-level `allOf` conditionals. Codex worked only because its adapter already
projected the schema. In the same session a real Codex implementer hit its usage
limit mid-milestone and the work had to be rescued by a manual takeover. With
one working reviewer and no controlled handoff, any single provider outage
stalled a run.

## Decision

**One canonical contract, per-adapter wire syntax.** The canonical schemas stay
the only contract. Each adapter may project a schema into the syntax its CLI
accepts, but only by relaxing it, and must validate answers against the
unchanged canonical schema. `review_contract.normalize_review` applies the
controller's semantic rules to every reviewer, so there is no
provider-specific review type. Projections refuse shapes they cannot express.

**Classify failures, decide rollover centrally.** Adapters classify an
unsuccessful invocation from the CLI's own error output into provider-neutral
kinds. Only provider-wide (quota, hard limit, unavailable) and session-scoped
(unresumable, exhausted) kinds can trigger rollover. Unknown output never does.

**Bounded, configured, verified rollover.** Rollover is opt-in config with
`max_rollovers` ≤ 1, an ordered replacement list, an approval mode and optional
trigger subset. The controller always writes a hashed handoff package first,
then decides: budget, configured trigger, allowed transition (a provider-wide
failure needs a different provider), replacement health. Blocked rollovers stop
HUMAN_BLOCKED; `approval: human` stops with the rollover prepared for
`autobuild resume`. Before takeover the handoff is re-verified against the live
repository. The replacement is a new session told to take over existing work,
never to continue a conversation it never had.

**Evidence is never inherited.** The replacement's source gets fresh Git
evidence, confined validation, browser gates and a fresh reviewer. Earlier
evidence remains history. Same-session resume and rollover are distinct modes
in `revision_history`, and the checkpoint carries `Autobuild-Rollover`.

## Alternatives Rejected

- Provider-specific review result types: two contracts would drift; syntax is
  the only real difference.
- Retrying or falling back on any error: silent provider switching hides
  defects (a schema rejection would just move to the other vendor) and breaks
  the "configuration names every provider" rule.
- Passing the failed provider's transcript to the replacement: it is
  provider-local, unverifiable and possibly wrong; the worktree and controller
  artifacts are the source of truth.
- Reviewer rollover in 0.6: reviewers are stateless fresh sessions, so choosing
  a working reviewer is configuration; automatic reviewer switching is deferred.

## Consequences

Claude and Codex can each fill any role. A quota or lost session no longer
needs a manual rescue when rollover is configured, and leaves a verified
handoff when it is not. The cost is one more decision record per failure and a
replacement that starts cold. Classification depends on CLI error text and must
be refreshed when a CLI changes its messages; unrecognised text fails safe as
`unknown`. Transient errors still stop for a human because 0.6 adds no automatic
retry.
