# Autobuild

Autobuild runs one approved implementation brief through an agent implementer
and a fresh, independent agent reviewer. It works in an isolated branch and
worktree, runs your project's checks itself in a sandbox, and stops for you.

- **Before it stops:** the run either passes review and every required check,
  then gets a commit on its own run branch, or it stops safely with a recorded
  reason and all work preserved.
- **What it never does:** merge, push, deploy, or cross a gate that needs a
  human.

## One-Time Machine Setup

Autobuild is installed once, from the AI Engineering Harness. It isn't copied
into projects.

```bash
python3 ~/ai-engineering-harness/scripts/setup/install.py --apply
cd ~/ai-engineering-harness/autobuild
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Setup links the command as `~/.local/bin/autobuild`, so you just type
`autobuild`. If setup reports that `~/.local/bin` is not on `PATH`, add
`export PATH="$HOME/.local/bin:$PATH"` to your shell profile and open a new
shell. Verify:

```bash
which autobuild     # ~/.local/bin/autobuild (links into the harness)
autobuild check     # schemas, policy and examples are consistent
```

Details are in the harness `docs/INSTALLATION.md`.

## Project Setup

A project only needs one directory of its own:

```text
your-project/
  .autobuild/
    config.yaml        # roles/providers, branches, paths, limits, validation commands
    runs/              # run artifacts, git-ignored (keep runs/.gitkeep)
  docs/roadmap/        # briefs from the planner (paths.roadmap)
  PROJECT_STATE.md     # paths.project_state
  docs/decisions/      # paths.adr_directory
```

To add Autobuild to an existing repository:

1. Copy [`templates/project-config.yaml`](templates/project-config.yaml) to
   `.autobuild/config.yaml`.
2. Fill in:
   - `agents` (which provider plans, implements and reviews);
   - `git.protected_branches`;
   - `paths`;
   - `validation.commands`, the checks Autobuild runs itself.
3. Add `.autobuild/runs/*` and `!.autobuild/runs/.gitkeep` to `.gitignore`.

The full contract is [`schemas/config.schema.json`](schemas/config.schema.json).

Validation commands run in a sandbox against a disposable copy of the run's
source snapshot (tracked and untracked files, not git-ignored ones):
- no network unless a command sets `network: host`;
- no inherited environment.

Write them as argv lists (`command: [npm, test]`) with an optional `cwd`.
Dependency directories your checks need but git ignores (for example `.venv`)
go in `validation.runtime_paths`; they are mounted read-only from your checkout.

## First-Time Validation

Run from the project root (not from inside `.autobuild/`):

```bash
autobuild config .   # the config matches the schema and its safety rules
autobuild agents .   # which provider fills each role, and its command
```

## Running An Implementation

```bash
autobuild brief docs/roadmap/M1.md                          # the brief is complete and approved
autobuild run docs/roadmap/M1.md --project . --dry-run      # every preflight check; creates nothing
autobuild run docs/roadmap/M1.md --project .                # the run
```

While and after a run:

```bash
autobuild stop <run-id> --project .                    # safe stop (needs control.provider: file)
autobuild resume <run-id> --project . [--dry-run]      # explicit human resume
autobuild resume <run-id> --project . --override-limits  # after raising a budget in config.yaml
autobuild evidence .autobuild/runs/<run-id>            # verify the run's evidence
```

Each run ends with a report and leaves its branch and worktree for you to
review. Merging is yours.

## Safety Model

- **Isolation:** every run works on its own `agent/...` branch in a separate
  worktree. Agents can't commit, push or touch protected branches; the
  controller makes the only commit.
- **Evidence:** only checks the controller ran itself, in its sandbox, count
  as evidence. A reviewer's PASS can't override a failed check.
- **Stopping:** budgets, remote stop and the autonomy policy (GREEN / YELLOW /
  RED) end a run safely, with a stated reason.

More in [docs/safety/SAFETY_MODEL.md](docs/safety/SAFETY_MODEL.md) and
[docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md);
[docs/README.md](docs/README.md) maps all documentation.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `autobuild: command not found` | Rerun `install.py --apply`. If it warns that `~/.local/bin` is not on `PATH`, add it to your shell profile and open a new shell. `~/.agents/autobuild/bin/autobuild` always works as a fallback. |
| `autobuild: no virtualenv at …/.venv` | Create the harness virtualenv (One-Time Machine Setup). |
| `FAIL .autobuild/config.yaml` | `autobuild config .` lists each problem with its field; compare with `templates/project-config.yaml`. |
| `environment key X is controller-owned or unsafe` | `PATH`, `HOME`, `PYTHONPATH`, proxy, loader and `AUTOBUILD_*` keys can't be set per command. Use the tool's own config instead (for example pytest's `pythonpath` in `pytest.ini`), `cwd`, or `runtime_paths`. |
| `Status: unavailable` for a provider | That provider's CLI is not on `PATH` or fails `--version`; install it or assign another provider in `agents`. |
| A validation command ERRORs with "No such file" | The tool isn't in the sandbox. Ignored dependencies need `runtime_paths` or a setup command; installs that download need `network: host`. |
| `validation runtime_path missing or unsafe` | The listed path must exist in your checkout, inside the project, and not be a symlink. |
| A command ends with exit `-25` (file size limit) | One file written by a validation command exceeded 64 MiB, the sandbox limit (common with `npm ci` for Next.js). Mount the installed tree with `runtime_paths` instead of installing during validation. |
| `EROFS: read-only file system` under a runtime path | The tool writes a cache into a mounted dependency tree. Point its cache elsewhere or use its no-cache option (for example vitest's `--configLoader runner`). |
| A command reads the wrong project | Run from the project root, or pass `--project <root>`. |

## Repository Layout

```text
autobuild/                 Python package, grouped by responsibility:
  core/                    run lifecycle: preflight, runner, run store and states, resume, config, report
  policy/                  autonomy gate, safety policy, secret detection, brief checks
  providers/               provider-neutral agent invocation, registry, failure classification
    adapters/              the only provider-specific code (Claude Code, Codex)
  rollover/                bounded implementer rollover and handoff
  git/                     worktree/branch isolation, snapshots, git guard, checkpoint decision
  validation/              confined normal validation and browser gates (shared sandbox)
  review/                  canonical reviewer contract and prompts
  governance/              budgets, runtime/usage accounting, stop reasons
  control/                 remote stop (file provider)
  notifications/           payload, rendering, console/file/email providers
  common/                  shared paths, YAML, JSON Schema, front matter
  cli.py, __main__.py      command-line entry points; fixtures.py backs `autobuild fixture`
schemas/                   JSON Schemas (config, implementation, run-state, review, validation, notification, …)
policy/                    autonomy.yaml, safety.yaml (data the policy/ package enforces)
providers/                 registry.yaml: the only place concrete agent providers are named
templates/                 brief, prompts, notification body, starter project config, fixtures
examples/                  GREEN / YELLOW / RED briefs, run state, reviews, validation
docs/                      architecture/, operations/, contracts/, safety/, evaluations/, decisions/
tests/                     pytest suite, including doc ↔ code and layout consistency checks
bin/autobuild              CLI wrapper using this directory's .venv
```

All commands: `autobuild --help`. Development: `.venv/bin/python -m pytest`
from this directory.
