"""Notifier that prints the rendered notification — the default provider and
the reference implementation for file/email providers in later phases."""

import sys
from typing import Any, TextIO

from autobuild.notifications.notification_format import format_notification


class ConsoleNotifier:
    def __init__(self, stream: TextIO = sys.stdout):
        self._stream = stream

    def send(self, payload: dict[str, Any]) -> None:
        print(format_notification(payload), file=self._stream)
