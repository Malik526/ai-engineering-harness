# Autobuild Architecture

Autobuild is a small, deterministic control plane that coordinates existing
coding agents through one engineering method: **plan with the human →
implement → validate → independent review → revise or pass → next item or
human gate**. It doesn't replace any agent capability. Planning, coding, code
review and browser automation stay with the agents and their skills.
Autobuild owns only what must not depend on a model's judgment: run state,
autonomy policy, the artifact contract, safety boundaries, stopping and
notifications.

## Roles

| Role | Filled by | Responsible for | Never does |
| --- | --- | --- | --- |
| Human | — | Architecture and product authority; approves plans; merges to protected branches; secrets; external accounts; production | — |
| Planner | configured provider | Interactive planning conversation, challenging assumptions, roadmap, approved briefs, autonomy classification | Starts implementation before explicit approval |
| Controller | Autobuild (deterministic code) | State machine, autonomy gate, worktree/branch isolation, stop handling, notifications | Asks a model whether to continue |
| Implementer | configured provider | Implements one approved brief inside its worktree, runs validation, updates docs, writes a summary | Approves its own work |
| Reviewer | configured provider, always a fresh session | Judges the brief against the actual diff and evidence; returns PASS / REVISE / BLOCKED | Treats the implementer's summary as evidence |

Providers (currently Claude Code and Codex) are assigned to roles in each
project's `.autobuild/config.yaml` `agents` block, and any provider may fill
any role. Orchestration code never refers to a specific provider. See
`PROVIDERS.md`. Independence comes from the **fresh reviewer session**, not
from the vendor: a reviewer session may never be a session the implementer
used (`run_state_checks.py` enforces this).

## Flow

```text
Human ⇄ Planner ──(explicit approval)──▶ approved brief (status: ready)
                                              │
                                              ▼
                                   Controller: autonomy gate
                                 ┌────────────┴────────────┐
                              continue                    stop ──▶ notify human
                                 │
                     isolated branch + worktree
                                 │
                                 ▼
                            Implementer ◀──────────────┐
                                 │                     │ findings
                                 ▼                     │
                    Validation (controller re-runs)    │
                                 │                     │
                                 ▼                     │
                     Fresh Reviewer ── REVISE ─────────┘
                        │        │
                      PASS     BLOCKED ──▶ HUMAN_BLOCKED ──▶ notify human
                        │
               checkpoint commit on run branch
                        │
            next roadmap item ──▶ autonomy gate (GREEN continues, else stop + notify)
```

Merging into a protected branch always stays outside autobuild.

## Run States

Defined in `autobuild/states.py`, mirrored in `schemas/run-state.schema.json`.

| State | Meaning |
| --- | --- |
| `IDLE` | No work selected |
| `PLANNING` | Planner and human are still discussing; nothing may execute |
| `READY` | An approved brief has passed the autonomy gate and is waiting to start |
| `IMPLEMENTING` | Implementer is working in the run's worktree |
| `VALIDATING` | Controller is re-running the validation commands |
| `REVIEWING` | A fresh reviewer session is judging the evidence |
| `REVISING` | Implementer is addressing review findings or failed validation |
| `PASSED` | Reviewer returned PASS; checkpoint commit pending or made |
| `HUMAN_BLOCKED` | A human gate was reached (YELLOW/RED item, BLOCKED review, review-cycle limit) |
| `FAILED` | Unrecoverable error; `failure` records why |
| `STOP_REQUESTED` | A remote stop was seen; the stop sequence is running |
| `STOPPED` | Stop sequence finished; worktree and uncommitted work preserved |
| `COMPLETED` | Run finished with a commit on its branch |

Transitions:

- Forward: `IDLE → PLANNING → READY → IMPLEMENTING → VALIDATING → REVIEWING → PASSED → COMPLETED`.
- Implementation-only runs (phase 0.2, `review_mode: none`): `READY → IMPLEMENTING → VALIDATING → COMPLETED`. The schema forbids such a run from entering review states or claiming a review; it completes *unreviewed* and waits for the human.
- Setup failures before implementation: `READY → FAILED`.
- Revision loop: `VALIDATING → REVISING` (validation failed) and `REVIEWING → REVISING → VALIDATING` (findings). A fix is always re-validated before it is re-reviewed.
- Exceeding `limits.max_review_cycles` moves the run to `HUMAN_BLOCKED`, never into another loop.
- `STOP_REQUESTED` can be entered from any working or waiting state, and leads only to `STOPPED`.
- Human-only resume: `HUMAN_BLOCKED`, `FAILED` and `STOPPED` → `READY`. The controller never resumes on its own.
- `COMPLETED` is terminal. The next roadmap item is a new run.

## Where Things Live

| Location | Contents |
| --- | --- |
| `~/ai-engineering-harness/autobuild/` (linked as `~/.agents/autobuild`) | Schemas, policy, provider registry, templates, controller code, docs |
| `~/ai-engineering-harness/skills/custom/implementation-planning/` | The planner skill |
| `<project>/.autobuild/config.yaml` | The project's role → provider assignments, branches, paths, limits, validation, notification and control settings |
| `<project>/.autobuild/runs/<run-id>/` | Run artifacts (git-ignored), see `ARTIFACT_CONTRACT.md` |
| `<project>/<paths.roadmap>` | Roadmap and briefs produced by the planner |

Projects keep their own `AGENTS.md`, ADRs, project state and changelog.
Autobuild points at them through `paths` and doesn't copy them.

## Phases

| Phase | Adds |
| --- | --- |
| 0.1 | Foundation: schemas, policy, state model, contracts, validators, planning skill |
| 0.2 | **Done.** Single-implementation runner (`autobuild run`): preflight, worktree/branch isolation, Claude Code and Codex adapters, command guard, controller validation, checkpoint commit. See `RUNNER.md` |
| 0.3 | Independent review loop with a hard cycle limit |
| 0.4 | Browser/E2E evidence through existing browser skills |
| 0.5 | Roadmap rollover through the autonomy gate |
| 0.6 | Operations: notification providers, remote stop provider, `/resume`, run history, spend limits |

Related: `RUNNER.md`, `PROVIDERS.md`, `AUTONOMY_POLICY.md`, `ARTIFACT_CONTRACT.md`, `SAFETY_MODEL.md`,
`CONTROL_CONTRACT.md`, `NOTIFICATION_CONTRACT.md`, `decisions/`.
