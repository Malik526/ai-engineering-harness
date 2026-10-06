# Control Contract — Remote Stop

The stop mechanism lives **outside every agent**. The controller polls a
`StopController` provider between agent operations, and while an operation is
running, then performs the stop sequence itself. Asking an agent to stop is
never the safety mechanism.

The interface is defined in `autobuild/control/control.py`:

| Method | Contract |
| --- | --- |
| `request_stop(run_id, requested_by, reason=None)` | Record a stop request. Idempotent. |
| `check_stop_requested(run_id)` | Return the pending `StopRequest` or `None`. Must be cheap enough to poll. |
| `acknowledge_stop(request)` | Mark the request handled after the stop sequence. Returns it with `acknowledged_at`. |

## Stop Sequence

Once `check_stop_requested` returns a request, the controller runs these
steps in order (`STOP_SEQUENCE`):

1. `block_new_operations`: no new agent or tool operation starts.
2. `terminate_current_operation`: the running child process gets a graceful termination signal, then a hard kill after a timeout.
3. `persist_run_state`: `state.json` is written with `stop_requested: true`.
4. `preserve_worktree`: the worktree isn't removed.
5. `preserve_uncommitted_work`: uncommitted changes aren't reset, stashed or discarded.
6. `record_stopped_state`: the state moves `STOP_REQUESTED → STOPPED`.
7. `emit_notification`: a notification is sent.
8. `exit_controller`: the controller exits.

Resuming is a human command. It moves `STOPPED → READY` and continues in the
preserved worktree.

## Providers

Selected by `control.provider` when `control.remote_stop_enabled` is true.
Preflight rejects a provider that is not implemented rather than ignoring it.

- `file` (implemented, 0.7): `autobuild stop RUN [--reason TEXT]` writes
  `<run>/control/stop.json` atomically; `autobuild stop RUN --clear` withdraws
  a pending request. Works from any shell on the machine running the
  controller (including over SSH).
- `github`: `/stop` and `/resume` comments on a private control issue, readable from a phone. Not implemented.
- `supabase`: a control table, if a web control panel is built later. Not implemented.

## Implementation (0.7)

`governance.Governor` checks the stop controller before every agent or tool
operation (implementation, validation, browser gates, review). While an
implementer or reviewer process runs, a watchdog thread polls the controller
every two seconds and terminates the provider's process group itself
(TERM, then KILL), so the stop never depends on the model. Validation and
browser commands are not interrupted mid-command; the stop takes effect at the
next boundary, bounded by their own timeouts.

After a stop the run is `STOPPED` with `stop_reason.code: remote_stop`, the
request is acknowledged (`acknowledged_at`), a `stopped` notification is sent,
and the worktree, branch, uncommitted changes and every artifact are kept. No
checkpoint is made by a stopped run. `autobuild resume` refuses while an
unacknowledged request is pending, so a stop is never silently overridden.

Ctrl-C on the controller follows the same sequence with
`stop_reason.code: interrupted`.
