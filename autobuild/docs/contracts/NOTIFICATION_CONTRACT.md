# Notification Contract

Notifications are deterministic software, not agent output.

- **When:** a run notifies once when it ends (`COMPLETED`, `HUMAN_BLOCKED`,
  `FAILED`, `STOPPED`) and once per executed provider rollover. `notifier.py`
  owns the rule; no model decides whether to send. `PASSED` is transient and
  never notified on its own.
- **What:** `notification_payload.run_payload` builds the payload from the run's
  own state and controller artifacts (validation, browser and review records)
  and validates it against `schemas/notification.schema.json`.
- **How:** a `Notifier` provider renders `templates/notification.md` and
  delivers it, selected by `notifications.provider` when `notifications.enabled`.

## Events

| Event | When |
| --- | --- |
| `completed` | `COMPLETED` |
| `failed` | `FAILED` (provider, safety or controller failure) |
| `stopped` | `STOPPED` by remote stop or Ctrl-C |
| `budget_exhausted` | `HUMAN_BLOCKED` because a governance budget ran out |
| `human_action_required` | `HUMAN_BLOCKED` by a reviewer BLOCK or a rollover awaiting approval |
| `blocked` | any other `HUMAN_BLOCKED` (validation/browser non-PASS, provider failure without rollover) |
| `rollover` | a replacement implementer took over (the run continues) |

## Payload Fields

| Field | Source |
| --- | --- |
| `run_id`, `status`, `branch`, `commit` | `state.json` |
| `event`, `stop_reason` | controller event; `state.stop_reason` code and detail |
| `project`, `implementation` | config `project.name`; brief `id`, `title` |
| `summary` | one line chosen by the controller (changed files, or the rollover); the only free text |
| `providers` | latest implementer and reviewer providers from `agent_sessions` |
| `counts` | implementation attempts, review cycles, executed rollovers |
| `validation` | latest controller validation: commands passed/failed, failed names, `authoritative` |
| `browser` | latest controller browser evidence: passed, gates passed/failed; null without gates |
| `review` | cycle count, initial and final status, corrections requested before the final review |
| `next_step` | the next roadmap item's gate decision (`none` for a single run) |
| `human_action` | `state.json` `human_gate.human_action` |
| `protected_branches` | configured names, and `modified` from the controller's ref comparison |

The rendered text reads on a phone in about 20 seconds: event and status, stop
reason, what changed, providers and counts, validation, browser, review, git,
human action.

## Providers

| Provider | Delivery |
| --- | --- |
| `console` | prints the rendered text |
| `file` | `<run>/notifications/NN-<event>.json` (payload) and `.txt` (rendered); never overwritten |
| `email` | SMTP (`notifications.email`: `to`, `from`, `smtp_host`, optional `smtp_port`, `security` starttls/ssl/none, `username_env`/`password_env`). Credentials come from the named environment variables only |

Delivery never affects the run: the state is persisted first, and a delivery
error is logged to `logs/controller.log` and `notifications/delivery-failures.log`.
