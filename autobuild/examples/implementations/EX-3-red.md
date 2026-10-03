---
id: "EX-3"
title: Rotate the credential encryption key
status: ready
autonomy: red
autonomy_rationale: Secret rotation invalidates every stored platform connection in production and cannot be undone by an agent.
depends_on: []
human_requirements:
  - Generate the new key and store it in the production secret store
  - Schedule user-facing downtime and re-connection messaging
external_requirements:
  - Production secret store access
acceptance:
  - All hosted connections are re-encrypted or users are prompted to reconnect
validation:
  tests_required: true
  browser_required: false
  human_validation_required: true
approval:
  approved_by: human
  approved_at: "2026-10-03"
---

# EX-3 — Rotate the credential encryption key

## Objective

Replace the at-rest encryption key for hosted platform credentials.

## Context

Security policy; credential storage module.

## Scope

- Human-run rotation procedure

## Non-Goals

- Any autonomous execution

## Acceptance Criteria

See front matter.

## Validation

Human-run, against production.

## Documentation

Runbook and CHANGELOG entry.

## Human Gate

RED — the human performs the whole implementation.
