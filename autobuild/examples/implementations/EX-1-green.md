---
id: "EX-1"
title: Enforce TikTok caption length limit before scheduling
status: ready
autonomy: green
depends_on: []
human_requirements: []
external_requirements: []
acceptance:
  - Captions longer than the platform limit are rejected with a clear validation error
  - Existing captions within the limit schedule exactly as before
  - Unit tests cover the boundary (limit, limit + 1)
validation:
  tests_required: true
  browser_required: false
  human_validation_required: false
approval:
  approved_by: human
  approved_at: "2026-10-03"
---

# EX-1 — Enforce TikTok caption length limit before scheduling

## Objective

Reject over-length captions at scheduling time instead of at publish time, so a
post cannot fail hours later on a check we could run up front.

## Context

Caption ownership ADR; scheduling package; publishing contract tests.

## Scope

- Add a caption-length check to the scheduling path
- Surface the error through the existing validation error type

## Non-Goals

- No change to caption generation or the publish client

## Acceptance Criteria

See front matter; each is verifiable from unit tests.

## Validation

`pytest`

## Documentation

CHANGELOG entry.

## Human Gate

None — GREEN.
