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

## Add Autobuild To A Project

A project only needs one directory of its own:

```text
your-project/
  .autobuild/
    config.yaml        # roles/providers, branches, paths, limits, validation commands
    runs/              # run artifacts, git-ignored (keep runs/.gitkeep)
  docs/roadmap/        # project-owned brief index and milestone folders (paths.roadmap)
  PROJECT_STATE.md     # paths.project_state
  docs/decisions/      # paths.adr_directory
```

From the project root:

```bash
mkdir -p .autobuild/runs docs/roadmap docs/decisions
cp ~/.agents/autobuild/templates/project-config.yaml .autobuild/config.yaml
cp ~/.agents/autobuild/templates/roadmap-README.md docs/roadmap/README.md
touch .autobuild/runs/.gitkeep docs/decisions/.gitkeep PROJECT_STATE.md
```

Then:

1. Fill in `.autobuild/config.yaml`:
   - `agents` (which provider plans, implements and reviews);
   - `git.protected_branches`;
   - `paths`, including the project-owned `docs/roadmap` root;
   - `validation.commands`, the checks Autobuild runs itself.
2. Add `.autobuild/runs/*` and `!.autobuild/runs/.gitkeep` to `.gitignore`.
3. Keep briefs below the configured roadmap root, normally as
   `docs/roadmap/<milestone>/<implementation-brief>.md`.

The full contract is [`schemas/config.schema.json`](schemas/config.schema.json).

Validation commands run in a sandbox against a disposable copy of the run's
source snapshot (tracked and untracked files, not git-ignored ones):
- no network unless a command sets `network: host`;
- no inherited environment.

Write them as argv lists (`command: [npm, test]`) with an optional `cwd`.
Dependency directories your checks need but git ignores (for example `.venv`)
go in `validation.runtime_paths`; they are mounted read-only from your checkout.

Validate the project setup:

Run from the project root (not from inside `.autobuild/`):

```bash
autobuild config .   # the config matches the schema and its safety rules
autobuild agents .   # which provider fills each role, and its command
```

## Plan An Implementation

Start Claude Code or Codex from the project root:

```bash
cd ~/your-project
codex          # or: claude
```

Ask it to use the implementation-planning workflow. Natural wording is fine:

> Use the implementation-planning workflow. I want to plan the next milestone.
> Do not finalize the brief until I approve the plan.

The planner reads the project paths from `.autobuild/config.yaml`, inspects only
the relevant state, ADRs, architecture and code, then discusses risks, scope,
dependencies, acceptance criteria and GREEN/YELLOW/RED autonomy with you. It
does not write an executable brief until you explicitly approve the plan.

After approval, the planner writes the brief below `paths.roadmap` using the
installed [`templates/implementation-brief.md`](templates/implementation-brief.md),
updates the roadmap index, validates the brief and reports its autonomy gate.
It stops there; planning never starts an Autobuild run.

The `implementation-planning` skill is installed for both Claude Code and Codex,
so you do not need to memorize a special command.

## Execute The Approved Brief

From the project root, using the path the planner reported:

```bash
autobuild brief docs/roadmap/<milestone>/<brief>.md
```

The starter config requires a clean Git tree. After the brief validates, review
and commit the approved roadmap files through your normal Git workflow; the
planner does not commit them. Then:

```bash
autobuild run docs/roadmap/<milestone>/<brief>.md --project . --dry-run
autobuild run docs/roadmap/<milestone>/<brief>.md --project .
```

The first command checks the brief schema and approval metadata. The dry-run
checks the project config, autonomy gate, dependencies, providers, Git state and
validation prerequisites without creating a branch, worktree or run. The final
command starts the isolated implementation only after those checks pass.

## Inspect And Control A Run

```bash
autobuild evidence .autobuild/runs/<run-id>            # verify controller-owned evidence
autobuild stop <run-id> --project .                    # safe stop (needs control.provider: file)
autobuild resume <run-id> --project . --dry-run        # inspect an explicit resume
autobuild resume <run-id> --project .                  # resume preserved work
autobuild resume <run-id> --project . --override-limits  # after raising a budget in config.yaml
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
