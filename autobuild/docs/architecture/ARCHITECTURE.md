# Autobuild Architecture

Autobuild is a small, deterministic control plane that coordinates existing
coding agents through one engineering method: **plan with the human →
implement → validate → independent review → revise or pass → stop for the
human**. Roadmap rollover is future work. It doesn't replace agent capabilities. Planning, coding, code
review stay with the agents. Browser automation uses existing project tooling,
but the controller owns its execution and deterministic truth.
Autobuild owns only what must not depend on a model's judgment: run state,
autonomy policy, the artifact contract, safety boundaries, stopping and
notifications.

## Roles

| Role | Filled by | Responsible for | Never does |
| --- | --- | --- | --- |
| Human | — | Architecture and product authority; approves plans; merges to protected branches; secrets; external accounts; production | — |
| Planner | configured provider | Interactive planning conversation, challenging assumptions, roadmap, approved briefs, autonomy classification | Starts implementation before explicit approval |
| Controller | Autobuild (deterministic code) | State machine, autonomy gate, worktree/branch isolation, confined validation, stop handling, notifications | Asks a model whether to continue |
| Implementer | configured provider | Implements one approved brief inside its worktree, runs validation, updates docs, writes a summary | Approves its own work |
| Reviewer | configured provider, always a fresh session | Judges the brief against the actual diff and evidence; returns PASS / REVISE / BLOCK | Edits code or treats implementer narrative as evidence |

Providers (currently Claude Code and Codex) are assigned to roles in each
project's `.autobuild/config.yaml` `agents` block, and any provider may fill
any role. Orchestration code never refers to a specific provider. See
[PROVIDERS.md](PROVIDERS.md). Independence comes from the **fresh reviewer session**, not
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
                                 │  quota/session failure ──▶ handoff ──▶ configured
                                 │  replacement (new session, max 1) or HUMAN_BLOCKED
                                 │                     │ findings
                                 ▼                     │
              Confined validation + browser gates     │
                                 │                     │
                                 ▼                     │
                     Fresh Reviewer ── REVISE ─────────┘
                        │        │
                      PASS     BLOCK / budget limit ──▶ HUMAN_BLOCKED
                        │
               checkpoint commit on run branch
                        │
              COMPLETED: stop for human (no roadmap rollover)
```

Merging into a protected branch always stays outside autobuild.

## Run States

Defined in `autobuild/core/states.py`, mirrored in `schemas/run-state.schema.json`.

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
| `HUMAN_BLOCKED` | Review BLOCK, exhausted budget or browser gate; work preserved |
| `FAILED` | Error; `failure` records reason and whether explicit resume is safe |
| `STOP_REQUESTED` | Interrupt seen; the stop sequence is running (remote stop is future work) |
| `STOPPED` | Stop sequence finished; worktree and uncommitted work preserved |
| `COMPLETED` | Controller validation and independent review passed; checkpoint if eligible |

Transitions:

- Forward: `IDLE → PLANNING → READY → IMPLEMENTING → VALIDATING → REVIEWING → PASSED → COMPLETED`.
- Implementation-only runs (phase 0.2, `review_mode: none`): `READY → IMPLEMENTING → VALIDATING → COMPLETED`. The schema forbids such a run from entering review states or claiming a review; it completes *unreviewed* and waits for the human.
- Setup failures before implementation: `READY → FAILED`.
- Implemented revision loop: `REVIEWING → REVISING → VALIDATING → REVIEWING` for findings. Normal/browser failures reach review so fixable failures can produce REVISE, but required non-PASS evidence can never checkpoint and reviewer PASS cannot override it. Every correction receives fresh evidence before a fresh review.
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
| `<project>/.autobuild/runs/<run-id>/` | Run artifacts (git-ignored), see [ARTIFACT_CONTRACT.md](../contracts/ARTIFACT_CONTRACT.md) |
| `<project>/<paths.roadmap>` | Roadmap and briefs produced by the planner |

Projects keep their own `AGENTS.md`, ADRs, project state and changelog.
Autobuild points at them through `paths` and doesn't copy them.

## Phases

| Phase | Adds |
| --- | --- |
| 0.1 | Foundation: schemas, policy, state model, contracts, validators, planning skill |
| 0.2 | **Done.** Single-implementation runner (`autobuild run`): preflight, worktree/branch isolation, Claude Code and Codex adapters, command guard, controller validation, checkpoint commit. See [RUNNER.md](../operations/RUNNER.md) |
| 0.3 | **Implemented.** Independent review, bounded revisions, read-only reviewers, per-cycle evidence and explicit CLI resume. See [RUNNER.md](../operations/RUNNER.md) and [EVALUATION_0_3.md](../evaluations/EVALUATION_0_3.md) for verification and live-provider limitations |
| 0.4 | **Implemented.** Controller-owned browser/E2E gates, isolated services, immutable evidence and hard checkpoint barriers. See [BROWSER_GATES.md](../operations/BROWSER_GATES.md), ADR 0004 and [EVALUATION_0_4.md](../evaluations/EVALUATION_0_4.md) |
| 0.5 | **Implemented.** Normal tests/lint/type checks/builds use the shared fail-closed Bubblewrap layer, exact disposable source snapshots, isolated environment/network policy, and immutable evidence. See [VALIDATION_CONFINEMENT.md](../safety/VALIDATION_CONFINEMENT.md), ADR 0005 and [EVALUATION_0_5.md](../evaluations/EVALUATION_0_5.md) |
| 0.6 | **Implemented.** Reviewer portability (one canonical review contract, per-adapter wire projections; Claude and Codex both review) and bounded implementer provider/session rollover through a verified handoff, with fresh validation, browser evidence and review after takeover. See [PROVIDERS.md](PROVIDERS.md), [RUNNER.md](../operations/RUNNER.md) → Rollover, ADR 0006 and [EVALUATION_0_6.md](../evaluations/EVALUATION_0_6.md) |
| 0.7 | **Implemented.** Bounded autonomous-run governance: controller-owned runtime/revision/review/rollover/validation/browser/token budgets checked before every operation, canonical stop reasons, file-based remote stop that terminates a running provider, structured notifications (console/file/email), and explicit `--override-limits` resume. See [RUNNER.md](../operations/RUNNER.md) → Governance, [CONTROL_CONTRACT.md](../contracts/CONTROL_CONTRACT.md), [NOTIFICATION_CONTRACT.md](../contracts/NOTIFICATION_CONTRACT.md), ADR 0007 and [EVALUATION_0_7.md](../evaluations/EVALUATION_0_7.md) |
| 0.8 | Recommended next: a phone-reachable control channel (GitHub-issue stop/resume) and roadmap rollover within one project — start the next approved GREEN brief only after a verified completion, under a run-spanning budget, never across YELLOW/RED gates |

Related: [RUNNER.md](../operations/RUNNER.md), [PROVIDERS.md](PROVIDERS.md), [AUTONOMY_POLICY.md](../safety/AUTONOMY_POLICY.md), [ARTIFACT_CONTRACT.md](../contracts/ARTIFACT_CONTRACT.md), [SAFETY_MODEL.md](../safety/SAFETY_MODEL.md),
[CONTROL_CONTRACT.md](../contracts/CONTROL_CONTRACT.md), [NOTIFICATION_CONTRACT.md](../contracts/NOTIFICATION_CONTRACT.md), [decisions/](../decisions/).

## Governance

The controller, not a model, decides whether a run may continue. `governance.py`
checks every budget and the remote-stop channel before each agent or tool
operation and watches running providers; `stop_reasons.py` gives every finished
run one canonical reason; notifications are built from controller records.
Governance wraps the review, evidence, confinement and rollover systems without
changing them: a governed stop preserves everything and never checkpoints,
merges or pushes. See [RUNNER.md](../operations/RUNNER.md) → Governance and ADR 0007.

## Provider Continuity

Provider identity is configuration, and so is any change of provider during a
run. An implementer that fails with a classified provider/session failure
(`provider_failures.py`) leaves a hashed handoff package; `rollover_policy.py`
allows at most one configured replacement, which starts a new session from the
worktree, brief and handoff — never from another provider's memory. Its work is
validated, browser-tested and reviewed afresh. Reviewers are always fresh
sessions; every reviewer's answer is normalized by `review_contract.py` into
the same canonical review. See [PROVIDERS.md](PROVIDERS.md) and ADR 0006.

## Shared Validation Confinement

Any deterministic result capable of permitting a checkpoint executes through
`sandbox.py`. Normal validation uses a minimal Bubblewrap root and a disposable
materialization of the exact synthetic Git tree; browser gates retain 0.4's
read-only host/runtime policy but use the same policy builder and lifecycle helper.
Both paths fail ERROR when isolation cannot be established and have no host fallback.
See [VALIDATION_CONFINEMENT.md](../safety/VALIDATION_CONFINEMENT.md) for filesystem, environment, network, evidence,
and compatibility details.

## Browser Ownership

Agents may consume browser evidence, but the Autobuild controller owns execution
and truth of deterministic browser gates. Config selects gates, not model inference.
`browser_runner.py` creates a fresh sandbox/output root per gate and attempt;
`browser_worker.py` owns service readiness, test exit and process cleanup.
`browser_artifacts.py` confines collection, and `browser_contract.py` checks
immutable evidence and identity before review, resumed implementation and checkpoint.
Gate failures reach the existing PASS/REVISE/BLOCK reviewer, never a second review
system. Required non-PASS evidence prevents checkpointing independently of review.
