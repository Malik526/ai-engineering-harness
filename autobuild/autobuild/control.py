"""Provider-independent remote stop contract.

A stop must never depend on an agent cooperating: the controller polls a
StopController between (and during) agent operations and runs STOP_SEQUENCE
itself. Providers (file, GitHub issue, Supabase table) implement the protocol
in later phases. Contract details: docs/CONTROL_CONTRACT.md.
"""

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class StopRequest:
    run_id: str
    requested_by: str
    requested_at: str  # ISO 8601 UTC
    reason: Optional[str] = None
    acknowledged_at: Optional[str] = None


class StopController(Protocol):
    """Interface every remote-stop provider implements."""

    def request_stop(self, run_id: str, requested_by: str, reason: Optional[str] = None) -> StopRequest:
        """Record a stop request for `run_id`. Idempotent."""
        ...

    def check_stop_requested(self, run_id: str) -> Optional[StopRequest]:
        """Return the pending stop request, or None. Must be cheap enough to poll."""
        ...

    def acknowledge_stop(self, request: StopRequest) -> StopRequest:
        """Mark the request handled after STOP_SEQUENCE finished; returns it with acknowledged_at set."""
        ...


# What the controller does, in order, once check_stop_requested returns a request.
STOP_SEQUENCE: tuple[str, ...] = (
    "block_new_operations",
    "terminate_current_operation",
    "persist_run_state",
    "preserve_worktree",
    "preserve_uncommitted_work",
    "record_stopped_state",
    "emit_notification",
    "exit_controller",
)
