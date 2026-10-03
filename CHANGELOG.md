# AI Engineering Harness — Changelog

## 2026-10-03

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
