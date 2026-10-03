# AI Engineering Harness — Changelog

## 2026-10-03

### Autobuild 0.1 — Foundation and Execution Contract

- `autobuild/`: deterministic contracts for planner → implementer →
  independent reviewer workflows. It doesn't invoke any agent yet.
- Schemas (JSON Schema 2020-12): project config, implementation brief front
  matter, run state, review, validation results, notification payload. Rules
  encoded in the schemas include: GREEN items have no human or external
  requirements; YELLOW items need a human gate; non-draft briefs need recorded
  approval; PASSED needs at least one review; REVISE needs findings; reviews
  must examine the brief and the git diff.
- `policy/autonomy.yaml` and `policy/safety.yaml` drive the autonomy gate
  (`autobuild gate`) and default-deny operation checks.
- Run state machine with human-only resume, plus config-aware checks: no runs
  on protected branches, branch prefix, review-cycle limit, and reviewer
  sessions must be fresh (never an implementer session).
- Artifact contract separating authoritative evidence, decision records and
  supplemental narrative. Validation counts as evidence only when the
  controller re-ran it.
- Remote stop interface (`StopController`, `STOP_SEQUENCE`), notifier
  interface, payload builder and console renderer. No real providers yet.
- Docs: ARCHITECTURE, AUTONOMY_POLICY, ARTIFACT_CONTRACT, SAFETY_MODEL,
  CONTROL_CONTRACT, NOTIFICATION_CONTRACT, ADR 0001.
- Examples: GREEN, YELLOW and RED briefs, run state, REVISE/PASS reviews,
  validation results.
- `skills/custom/implementation-planning`: planner skill, linked to
  `~/.agents/skills` and `~/.codex/skills`. Not linked to Claude Code, which
  is the default implementer.
- Validation: `pytest` 67 passed, including doc/code consistency tests;
  `autobuild check` all OK.

### Harness — Establish Version-Controlled Harness Repository

- New repository `~/ai-engineering-harness`, the canonical source for reusable
  agent policies, custom skills and harness tooling.
- Global policies (`CODING`, `DOCUMENTATION`, `EXECUTION`, `GIT`, `SECURITY`,
  `VERIFICATION`) moved to `policies/global/`. `~/.agents/<NAME>.md` are now
  symlinks to them, so the existing `~/.claude/CLAUDE.md` and
  `~/.codex/AGENTS.md` adapters work unchanged.
- `scripts/setup/install.py` and `links.manifest`: check / apply / adopt
  runtime symlinks. Never overwrites a differing target. Originals are backed
  up to `~/.agents/.harness-backup/`.
- Docs: `ARCHITECTURE.md` (source of truth, ownership classes, why symlinks),
  `INSTALLATION.md`, `SKILL_MANAGEMENT.md` (inventory and classification).
- Left out on purpose: vendor skills (`sanity-*`, claude.ai synced), runtime
  state, the runtime adapters, and the Growth Agency `lead-capture-data-contract`
  skill.
- Validation: secret scan of migrated files clean; content verified identical
  before adoption; both adapters' policy paths resolve through the links.
