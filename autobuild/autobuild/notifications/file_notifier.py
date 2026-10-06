"""Notifier that writes each notification into the run directory.

`notifications/NN-<event>.json` is the validated payload and `.txt` the
rendered, phone-readable text. Files are written atomically and never
overwritten, so the run keeps an ordered record of what the operator was told.
"""

import json
import os
from pathlib import Path
from typing import Any

from autobuild.notifications.notification_format import format_notification


class FileNotifier:
    def __init__(self, run_dir: Path):
        self.directory = run_dir / "notifications"

    def send(self, payload: dict[str, Any]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        index = len(list(self.directory.glob("*.json"))) + 1
        stem = self.directory / f"{index:02d}-{payload['event']}"
        for suffix, text in ((".json", json.dumps(payload, indent=2) + "\n"), (".txt", format_notification(payload))):
            temporary = stem.with_suffix(suffix + ".tmp")
            temporary.write_text(text)
            os.replace(temporary, stem.with_suffix(suffix))
        return stem.with_suffix(".txt")
