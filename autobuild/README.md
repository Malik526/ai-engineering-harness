# Autobuild

The deterministic control plane for planner → implementer → independent
reviewer workflows. **Phase 0.1:** contracts and validators only. Nothing here
invokes an agent yet.

Read `docs/ARCHITECTURE.md` first.

## Layout

```text
autobuild/        Python package: states, autonomy gate, safety checks, artifact
                  contract, stop interface, notification payload/rendering, CLI
schemas/          JSON Schemas (config, implementation, run-state, review,
                  validation, notification)
policy/           autonomy.yaml, safety.yaml (data the controller enforces)
providers/        registry.yaml: the only place concrete agent providers are named
templates/        implementation brief, implementation summary, review,
                  notification body, starter project config
examples/         GREEN / YELLOW / RED briefs, run state, reviews, validation
docs/             ARCHITECTURE, PROVIDERS, AUTONOMY_POLICY, ARTIFACT_CONTRACT, SAFETY_MODEL,
                  CONTROL_CONTRACT, NOTIFICATION_CONTRACT, decisions/
tests/            pytest suite, including doc ↔ code consistency checks
bin/autobuild     CLI wrapper using this directory's .venv
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
```

`bin/autobuild` resolves symlinks, so `~/.agents/autobuild/bin/autobuild`
works from any directory.

## Adopting in a Project

Copy `templates/project-config.yaml` to `<project>/.autobuild/config.yaml`,
add `.autobuild/runs/*` (keeping `.gitkeep`) to the project's `.gitignore`,
and run `autobuild config <project>`.
