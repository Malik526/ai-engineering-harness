# 0003 - Bounded Independent Review And Explicit Resume

**Status:** Accepted, 2026-10-04

## Context

The 0.2 runner stopped after controller validation. Existing review schemas,
role assignments and states anticipated review but did not execute it. Revision
and resume must preserve evidence without relying on agent narrative or giving
reviewers code-writing authority.

## Decision

- Every new run uses independent review. Every reviewer gets a new adapter and
  context, never an implementer resume session. Returned session identities are
  checked against all prior sessions, including same-provider roles.
- Use the existing review schema: PASS, REVISE and BLOCK; normalize legacy
  BLOCKED. The controller validates contract/identity/evidence and owns workflow.
- Persist per-attempt Git snapshot trees and cumulative diffs plus validation
  logs and per-cycle review/process artifacts. Do not commit each revision.
  Latest artifact aliases remain for compatibility.
- REVISE resumes the recorded implementer with structured findings, then
  revalidates and starts a fresh reviewer. Failed validation/provider calls stop;
  no unbounded autonomous recovery. Count every review invocation against the
  budget, including invalid/failed/interrupted reviews.
- Only independent PASS reaches existing checkpoint eligibility. This narrows
  ADR 0002's human-gate checkpoint rule: BLOCK and exhausted review budget do
  not checkpoint; a PASS followed by a browser gate may still checkpoint.
- Resume requires explicit human CLI action, an eligible state, unchanged
  execution configuration except review budget, frozen brief, preserved branch/
  HEAD/repository and unchanged protected refs. Histories and budgets do not reset.
- Reviewer providers use native read-only controls plus hook/Git restrictions
  and post-execution snapshot checks. API schema projection is adapter-owned;
  the full local review contract remains authoritative.

## Consequences

One implementation can self-correct without copy/paste while remaining bounded
and provider-neutral. No merge, push, deployment, provider fallback, browser
certification or roadmap rollover is introduced. Old implementation-only runs
lack resume evidence and are refused. Human edits to protected refs also require
a new run. Hard controller crashes may leave a lock requiring human inspection.
Ignored-file/process side effects remain outside the Git snapshot boundary;
Claude implementer Bash confinement retains the documented 0.2 limitation.
