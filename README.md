# AI Engineering Harness

The version-controlled source of truth for the reusable parts of my AI
engineering workflow: global agent policies, custom skills, and the
`autobuild` framework. Agent runtimes (Claude Code, Codex) consume these
files through symlinks. Nothing here belongs to a single application.

## What Belongs Here

- **Global policies** (`policies/global/`): vendor-neutral coding, documentation, execution, git, security and verification rules.
- **Custom skills** (`skills/custom/`): workflow skills written for this harness and reusable across projects.
- **Customized vendor skills** (`skills/customized/`): upstream skills with local changes, with provenance recorded.
- **Frameworks and scripts:** `autobuild/` and `scripts/setup/`.
- **Harness documentation** (`docs/`), including the policy enforcement
  matrix and evaluation records.

## What Doesn't Belong Here

- Vendor-managed skills installed by a skill installer (for example the `sanity-*` skills in `~/.agents/skills`) or synced from claude.ai (`~/.claude/skills/synced`).
- Runtime state: sessions, caches, logs, auth files, memory, `~/.codex/config.toml`.
- Secrets of any kind.
- Project-specific context: roadmaps, ADRs, project state, and project-scoped skills such as `lead-capture-data-contract`, which belong to Growth Agency.
- The runtime adapters `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`. They stay thin, per-runtime files that reference the policies here (see `docs/INSTALLATION.md`).

## Supported Runtimes

- **Claude Code:** reads `~/.claude/CLAUDE.md`, which imports `~/.agents/*.md`, and skills in `~/.claude/skills/`.
- **Codex:** reads `~/.codex/AGENTS.md`, which points to `~/.agents/*.md`, and skills in `~/.codex/skills/` (and, depending on version, `~/.agents/skills/`).

## Layout

```text
policies/global/      global policies, linked to ~/.agents/<NAME>.md
skills/custom/        custom skills (implementation-planning)
autobuild/            autobuild framework, linked to ~/.agents/autobuild; CLI linked as ~/.local/bin/autobuild
scripts/setup/        links.manifest + install.py (check / apply / adopt links),
                      runtime_guards.py (merge owned runtime fragments),
                      audit_instructions.py (verify the policy → adapter chain and commit guards)
runtime/              provider guard definitions and policy-reference adapter fragments
scripts/hooks/        git_commit_guard.py (Claude Code: recognized commits ask the human)
scripts/tests/        tests for the harness scripts
scripts/evaluations/  opt-in manual runtime fixtures and measured completion behavior
docs/                 ARCHITECTURE, INSTALLATION, SKILL_MANAGEMENT,
                      RUNTIME_GUARDS, POLICY_ENFORCEMENT_MATRIX, evaluations and ADRs
CHANGELOG.md
```

Start with `docs/ARCHITECTURE.md`. To install on a machine, see
`docs/INSTALLATION.md`. Installation also puts the `autobuild` command on
`~/.local/bin`. To use Autobuild in a project, see
[autobuild/README.md](autobuild/README.md).

## Manual completion

Both runtime adapters invoke the shared lightweight [manual completion check](scripts/manual/README.md)
before the final summary. It verifies Git state, fresh validation evidence,
documentation reconciliation records and existing secret-like filename checks.
It never commits or creates branches/worktrees and skips Autobuild runs.
