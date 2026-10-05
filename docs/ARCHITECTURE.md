# Harness Architecture

## Source of Truth

```text
~/ai-engineering-harness   (this git repo — canonical)
        │  scripts/setup/install.py reads scripts/setup/links.manifest
        ▼
absolute symlinks in runtime locations
  ~/.agents/<POLICY>.md          ← policies/global/<POLICY>.md
  ~/.agents/autobuild            ← autobuild/
  ~/.agents/skills/<skill>       ← skills/custom/<skill>
  ~/.codex/skills/<skill>        ← skills/custom/<skill>
  ~/.claude/skills/<skill>       ← skills/custom/<skill>
        │
        ▼
thin runtime adapters (not in this repo)
  ~/.claude/CLAUDE.md   imports  ~/.agents/*.md
  ~/.codex/AGENTS.md    points to ~/.agents/*.md
```

Edits always happen in this repository. A runtime path that's a symlink into
this repo is a view, not a copy. `install.py` (check mode) reports any
runtime path that has drifted into an independent copy.

## Policy Enforcement Model

Global policy is the intent layer. Deterministic mechanisms reinforce only the
rules that can be checked reliably without harming normal work: instruction
wiring audits, runtime commit prompts, Claude Code hooks, Codex execpolicy
rules, Autobuild Git guards, schemas and configured validation commands.

`docs/POLICY_ENFORCEMENT_MATRIX.md` records each meaningful global rule, its
classification, current mechanism, gap and status. `scripts/setup/audit_instructions.py`
is the read-only health check for the instruction chain and verifies that the
matrix covers every canonical policy in `policies/global/`.

Autobuild controls remain opt-in and controller-owned. Manual development uses
the always-on global policies and runtime-level safety guards, but it does not
inherit Autobuild checkpoint commits or autonomous state transitions.

### Why Symlinks

Symlinks keep exactly one copy of each file, so a runtime can't drift from the
repo, and `git diff` shows every change regardless of which agent made it.
Both runtimes follow symlinks for instruction imports and skill directories.
A sync/copy script was rejected because copies drift, and a copied file
edited in a runtime location would silently lose its changes on the next
sync.

### Why the Adapters Stay Outside

`~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` are runtime adapters. They hold
the runtime-specific wording and routing, and import the shared policy by
path. Keeping them per-runtime lets each vendor's file format and loading
rules change without touching the canonical policy. Because they reference
the stable `~/.agents/*.md` paths, moving the policies into this repo didn't
require editing either adapter.

## Ownership Classes

| Class | Examples | In this repo? |
| --- | --- | --- |
| Custom | global policies, custom skills, autobuild | Yes, canonical |
| Customized vendor | upstream skill with local edits | Yes, under `skills/customized/` with provenance |
| Vendor | installer-managed skills (`.skill-lock.json`), claude.ai-synced skills | No |
| Runtime | sessions, caches, logs, auth, memory, CLI config | No |
| Project-specific | roadmaps, ADRs, project skills | No, lives in the project repo |

## Relationship to Project Repositories

Projects (Content Automation / Pickle Batch, Growth Agency, FirstMove…) keep
their own `AGENTS.md`, roadmap, project state, ADRs and changelog. They
consume the harness through the global policies and skills, and later through
`autobuild`'s per-project `.autobuild/config.yaml`. The harness never holds a
project's engineering context.
