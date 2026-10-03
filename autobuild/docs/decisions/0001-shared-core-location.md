# 0001 — Autobuild Lives in the Harness Repo; Projects Hold Only Config

**Status:** Accepted, 2026-10-03

## Context

The first brief placed schemas, templates, policy docs and scripts inside each
project repository, while also describing the engine as reusable across
projects (Content Automation, FirstMove, the portfolio, client work).
Following that layout would copy the contracts into every project and let
them drift apart.

## Decision

- Schemas, policy, templates, controller code and contract docs live once, at
  `autobuild/` in the AI engineering harness repository
  (`~/ai-engineering-harness`). The harness setup links it to the stable path
  `~/.agents/autobuild`, which is how skills, docs and projects refer to it.
- Each project owns only `.autobuild/config.yaml` and its git-ignored
  `.autobuild/runs/`.
- Workflow skills (such as `implementation-planning`) are harness skills under
  `skills/custom/`, linked only to the runtimes whose role uses them.
- Autobuild keeps its own policy YAML (`policy/`). Those files define the
  framework's behavior, unlike the harness's global prose policies.
- Autobuild has its own virtualenv and runs through `bin/autobuild`, so it
  doesn't depend on any project's Python environment.

## Consequences

- Contract changes happen in one place and are versioned with the harness.
  Projects pick them up immediately, so schema changes must stay backward
  compatible or bump `version` / `schema_version`.
- A project can't silently weaken the shared policy. Project config can only
  choose among values the schema allows.
