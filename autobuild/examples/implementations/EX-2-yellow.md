---
id: "EX-2"
title: Instagram OAuth connection
status: ready
autonomy: yellow
autonomy_rationale: Requires a Meta developer app and new client credentials that only the human can create and supply.
depends_on: ["EX-1"]
human_requirements:
  - Create and configure the Meta developer application
  - Register the OAuth redirect URI
  - Add the client id and secret through the approved secret workflow
external_requirements:
  - Meta developer account
acceptance:
  - Connect / callback / disconnect endpoints mirror the TikTok connection flow
  - Tokens are encrypted at rest with the existing credential encryption key
  - Browser flow reaches the Meta consent screen from Settings
validation:
  tests_required: true
  browser_required: true
  human_validation_required: true
approval:
  approved_by: human
  approved_at: "2026-10-03"
---

# EX-2 — Instagram OAuth connection

## Objective

Let a signed-in user connect an Instagram account the same way they connect TikTok.

## Context

Real-authentication ADR; TikTok connection endpoints.

## Scope

- Instagram connect, callback, and disconnect endpoints
- Settings UI entry point

## Non-Goals

- Publishing to Instagram (later item)

## Acceptance Criteria

See front matter. The last criterion needs a real Meta app, so the human validates it.

## Validation

`pytest`, browser flow up to the consent screen.

## Documentation

ADR addendum, CHANGELOG entry.

## Human Gate

Agents may write the endpoints and tests against a mocked provider. The run
stops before any step that needs the real Meta app or credentials.
