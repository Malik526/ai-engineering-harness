# Notification Contract

Notifications are deterministic software, not agent output.

- **When:** `autobuild/notifier.py` `should_notify` returns true when a run
  enters `PASSED`, `HUMAN_BLOCKED`, `FAILED`, `STOPPED` or `COMPLETED`. No
  model decides whether to send.
- **What:** `autobuild/notification_payload.py` builds the payload from
  structured data only: run state, brief metadata, `validation.json`, review
  results and the next item's gate decision. It validates the payload against
  `schemas/notification.schema.json`.
- **How:** a `Notifier` provider renders and delivers it. `ConsoleNotifier`
  renders `templates/notification.md`. File and email providers come in 0.6
  and are selected by `notifications.provider`.

## Payload Fields

| Field | Source |
| --- | --- |
| `run_id`, `status`, `branch`, `commit` | `state.json` |
| `project` | `project.name` in the config |
| `implementation` | brief `id`, `title` |
| `summary` | one line chosen by the controller; the only free text |
| `validation` | counts from `validation.json`; `authoritative` is false unless the controller produced it |
| `review` | cycle count, initial and final status, corrections requested before the final review |
| `next_step` | the next item's gate decision: `continue`, `stop` (with reasons) or `none` |
| `human_action` | `state.json` `human_gate.human_action`, plus the next item's `human_requirements` when the gate stops |
| `protected_branches` | configured names, and `modified` from the controller's before/after ref comparison |

The rendered text is meant to be read on a phone in about 20 seconds: status,
what changed, validation, review, git, next step, human action.
