"""Notifier provider interface, provider selection, and the rule for when a notification is sent.

Whether to notify is decided here from state changes and controller events,
never by an agent. A run notifies once when it ends (COMPLETED, HUMAN_BLOCKED,
FAILED or STOPPED) and once per executed provider rollover.
"""

from pathlib import Path
from typing import Any, Optional, Protocol

from autobuild.states import RunState

# Final states worth interrupting the human for. PASSED is transient (COMPLETED follows).
NOTIFY_ON: frozenset[RunState] = frozenset(
    {RunState.HUMAN_BLOCKED, RunState.FAILED, RunState.STOPPED, RunState.COMPLETED}
)


class Notifier(Protocol):
    """Delivers a validated notification payload (notification.schema.json)."""

    def send(self, payload: dict[str, Any]) -> None: ...


def should_notify(previous: Optional[RunState], current: RunState) -> bool:
    """True when the run just entered a state in NOTIFY_ON."""
    return current != previous and current in NOTIFY_ON


def load_notifier(config_data: dict[str, Any], run_dir: Path) -> Optional[Notifier]:
    """The configured provider, or None when notifications are disabled."""
    settings = config_data["notifications"]
    if not settings["enabled"]:
        return None
    if settings["provider"] == "file":
        from autobuild.file_notifier import FileNotifier
        return FileNotifier(run_dir)
    if settings["provider"] == "email":
        from autobuild.email_notifier import EmailNotifier
        return EmailNotifier(settings["email"])
    from autobuild.console_notifier import ConsoleNotifier
    return ConsoleNotifier()
