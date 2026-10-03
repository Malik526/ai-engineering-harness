# Autonomy Policy

The planner gives every implementation one autonomy class in its brief's front
matter. The controller applies `policy/autonomy.yaml` to that metadata
(`autobuild/autonomy.py`). No model decides whether work continues.

Check a brief with `autobuild gate <brief> --done <completed ids>`.

## GREEN

Runs without the human, and may roll over into the next eligible item.

All of these must hold. The schema rejects a GREEN brief that violates the
first three.

- `human_requirements` is empty. No new secret, account or manual approval is needed.
- `external_requirements` is empty. Every credential and service it needs already exists.
- `validation.human_validation_required` is false. Automated tooling can check the acceptance criteria.
- No destructive production operation, production deployment or billing action.

Examples: a validation rule with unit tests, a refactor behind existing tests,
a UI change verifiable by browser automation, documentation updates.

## YELLOW

Agents may prepare work, but the run stops at a defined human gate. The schema
requires at least one `human_requirements` entry and an `autonomy_rationale`.
Until prepare-only execution exists (after 0.5), the controller stops before
starting a YELLOW item.

Examples: OAuth or developer-dashboard configuration, adding credentials,
migrations that need production approval, infrastructure changes, integrations
that need manual account actions.

## RED

Autonomous execution is prohibited. The human performs the work, and the
schema requires an `autonomy_rationale`.

Examples: destructive production database operations, billing changes, account
ownership changes, secret rotation, protected production deployment, force
pushes to protected branches.

## Start Conditions

These apply to every class and live in `start_conditions` in
`policy/autonomy.yaml`. The controller starts an item autonomously only when
its class has `execution: autonomous` **and** all of these hold:

| Condition | Rule |
| --- | --- |
| `require_status_ready` | `status` is `ready`, meaning the human approved it |
| `require_dependencies_done` | every `depends_on` id is completed |
| `require_no_human_requirements` | `human_requirements` is empty |
| `require_no_external_requirements` | `external_requirements` is empty |
| `require_no_human_validation` | `validation.human_validation_required` is false |

Any failed condition gives `action: stop` with a reason for each failure.
Those reasons go into the notification.

## Approval

A brief stays `status: draft` while it is being discussed. Every other status
requires an `approval` block (`approved_by`, `approved_at`). The planner
writes it only after the human explicitly approves the plan. See
the harness skill `skills/custom/implementation-planning/SKILL.md`.
