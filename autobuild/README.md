# Autobuild

The deterministic control plane for planner → implementer → independent
reviewer workflows. One approved brief runs in an isolated worktree:

- **Validation:** controller-owned confined validation and browser gates.
- **Review:** a fresh independent reviewer, with bounded revision of the same
  session.
- **Rollover:** bounded provider rollover through a verified handoff.
- **Governance:** budgets, remote stop and notifications.

A PASS reaches eligible controller checkpointing, then the run stops for the
human. There is no merge, push or roadmap rollover.

Read [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md)
first; [docs/README.md](docs/README.md) maps all documentation.

## Layout

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

## Setup

```bash
cd ~/ai-engineering-harness/autobuild
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
bin/autobuild check
```

## CLI

```bash
autobuild check                         # self-check schemas, policy, examples
autobuild config [PROJECT]              # validate PROJECT/.autobuild/config.yaml
autobuild brief FILE...                 # validate implementation briefs
autobuild state FILE [--project DIR]    # validate a run state
autobuild review FILE... | validation FILE...
autobuild gate FILE --done ID,...       # autonomy gate decision for a brief
autobuild agents [PROJECT]              # resolved role -> provider assignment
autobuild run BRIEF [--dry-run] [--yes] [--base BRANCH] [--project DIR]
autobuild resume RUN [--dry-run] [--override-limits] [--project DIR]
autobuild stop RUN [--reason TEXT] [--clear] [--project DIR]
autobuild evidence RUN [--attempt N]    # verify validation, browser and handoff evidence
autobuild fixture create --implementer ID [--browser] | list | clean [NAME...|--all] [--legacy PATH...] [--yes]
```

`bin/autobuild` resolves symlinks, so `~/.agents/autobuild/bin/autobuild`
works from any directory.

## Adopting in a Project

Copy `templates/project-config.yaml` to `<project>/.autobuild/config.yaml`,
add `.autobuild/runs/*` (keeping `.gitkeep`) to the project's `.gitignore`,
and run `autobuild config <project>`.
