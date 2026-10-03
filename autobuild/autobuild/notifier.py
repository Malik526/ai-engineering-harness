"""Notifier provider interface and the rule for when a notification is sent.

Whether to notify is decided here from state changes, never by an agent.
"""

from typing import Any, Optional, Protocol

from autobuild.states import RunState

# States worth interrupting the human for.
NOTIFY_ON: frozenset[RunState] = frozenset(
    {RunState.PASSED, RunState.HUMAN_BLOCKED, RunState.FAILED, RunState.STOPPED, RunState.COMPLETED}
)


class Notifier(Protocol):
    """Delivers a validated notification payload (notification.schema.json)."""

    def send(self, payload: dict[str, Any]) -> None: ...


def should_notify(previous: Optional[RunState], current: RunState) -> bool:
    """True when the run just entered a state in NOTIFY_ON."""
    return current != previous and current in NOTIFY_ON
