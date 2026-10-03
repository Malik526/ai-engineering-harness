# Control Contract — Remote Stop

The stop mechanism lives **outside every agent**. The controller polls a
`StopController` provider between agent operations, and while an operation is
running, then performs the stop sequence itself. Asking an agent to stop is
never the safety mechanism.

The interface is defined in `autobuild/control.py`:

| Method | Contract |
| --- | --- |
| `request_stop(run_id, requested_by, reason=None)` | Record a stop request. Idempotent. |
| `check_stop_requested(run_id)` | Return the pending `StopRequest` or `None`. Must be cheap enough to poll. |
| `acknowledge_stop(request)` | Mark the request handled after the stop sequence. Returns it with `acknowledged_at`. |

## Stop Sequence

Once `check_stop_requested` returns a request, the controller runs these
steps in order (`STOP_SEQUENCE`):

1. `block_new_operations`: no new agent operation starts.
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

0.1 defines the interface only. Planned providers, selected by
`control.provider`:

- `file`: a stop file in the run directory, for local use and tests.
- `github`: `/stop` and `/resume` comments on a private control issue, readable from a phone.
- `supabase`: a control table, if a web control panel is built later.
