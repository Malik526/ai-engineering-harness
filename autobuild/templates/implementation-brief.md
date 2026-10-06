---
# Read by the controller; validate with: autobuild brief <file>
# Rules: docs/safety/AUTONOMY_POLICY.md. Quote dates and ids that look like numbers.
id: "M0.0"
title: Short imperative title
status: draft            # draft until the human explicitly approves the plan
autonomy: green          # green | yellow | red
# autonomy_rationale: required for yellow and red — why this needs a human
depends_on: []
human_requirements: []   # green: must be empty; yellow: at least one
external_requirements: [] # green: must be empty
acceptance:
  - Observable, automatically checkable outcome
validation:
  tests_required: true
  browser_required: false
  human_validation_required: false   # green: must be false
# approval:               # required once status leaves draft
#   approved_by: human
#   approved_at: "YYYY-MM-DD"
---

# <id> — <title>

## Objective

What this implementation achieves and why, in two to four sentences.

## Context

Pointers to the ADRs, docs, and code paths the implementer must read first.
Point to them; do not copy them.

## Scope

- Concrete change 1
- Concrete change 2

## Non-Goals

- What must not change, including adjacent work deferred to later items

## Acceptance Criteria

Expanded form of the `acceptance` list: each item says how a reviewer can
verify it from the diff, the tests, or browser evidence.

## Validation

Commands the controller will run, and for `browser_required` the flows to exercise.

## Documentation

Changelog, ADR, and project-state updates the repository's policy requires.

## Human Gate

Yellow/red only: exactly what the human must do, and what the agents may
prepare before stopping.
