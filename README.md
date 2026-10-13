# AI Engineering Harness

The version-controlled source of truth for the reusable parts of my AI
engineering workflow: global agent policies, custom skills, and the
`autobuild` framework. Agent runtimes (Claude Code, Codex) consume these
files through symlinks. Nothing here belongs to a single application.

## What You Get

- **The base harness** works on its own:
  - shared engineering policies (`policies/global/`) that Claude Code and Codex both load through thin adapters
  - deterministic safeguards: runtime commit guards, an instruction-chain audit, and a manual completion check agents run before reporting work done
  - reusable workflow skills
- **Autobuild** (`autobuild/`) is optional. It runs one approved brief through an implementer agent and an independent reviewer agent in an isolated worktree. You don't need it to use the base harness.

## Quick Start

You need Git and Python 3. Claude Code and/or Codex are detected if installed.
`--check` is read-only. `--apply` links files into `~/.agents`, `~/.local/bin`
and your installed providers' config directories, and merges harness-owned
sections into existing Claude/Codex config without replacing it. Run `--check`
first to see what it will touch.

```bash
git clone https://github.com/Malik526/ai-engineering-harness.git ~/ai-engineering-harness
cd ~/ai-engineering-harness
python3 scripts/setup/install.py --check
python3 scripts/setup/install.py --apply
python3 scripts/setup/audit_instructions.py
```

That installs the base harness. [docs/INSTALLATION.md](docs/INSTALLATION.md)
covers each step, setup statuses, and migrating a machine that already has
these files. To use Autobuild as well, follow
[autobuild/README.md](autobuild/README.md).

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
