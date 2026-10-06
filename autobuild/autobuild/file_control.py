"""File-backed remote stop (`control.provider: file`), the baseline StopController.

`autobuild stop RUN` writes `<run>/control/stop.json`; the controller polls it
between operations and, through the governor's watchdog, while a provider runs.
Writes are atomic renames, so a poll never reads a half-written request. The
controller acknowledges a request after the stop sequence; an acknowledged
request no longer stops anything, so a later resume can run.
"""

import json
import os
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Optional

from autobuild.control import StopRequest
from autobuild.run_store import utc_now

STOP_FILE = "control/stop.json"


class FileStopController:
    def __init__(self, run_dir: Path):
        self.path = run_dir / STOP_FILE

    def _write(self, request: StopRequest) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(request), indent=2) + "\n")
        os.replace(temporary, self.path)

    def _read(self) -> Optional[StopRequest]:
        try:
            return StopRequest(**json.loads(self.path.read_text()))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError):
            # An unreadable request still means someone asked to stop: fail toward stopping.
            return StopRequest(run_id="unknown", requested_by="unreadable stop file", requested_at=utc_now())

    def request_stop(self, run_id: str, requested_by: str, reason: Optional[str] = None) -> StopRequest:
        pending = self.check_stop_requested(run_id)
        if pending is not None:
            return pending
        request = StopRequest(run_id=run_id, requested_by=requested_by, requested_at=utc_now(), reason=reason)
        self._write(request)
        return request

    def check_stop_requested(self, run_id: str) -> Optional[StopRequest]:
        request = self._read()
        if request is None or request.acknowledged_at is not None:
            return None
        return request

    def acknowledge_stop(self, request: StopRequest) -> StopRequest:
        acknowledged = replace(request, acknowledged_at=utc_now())
        self._write(acknowledged)
        return acknowledged

    def clear(self) -> bool:
        """Withdraw a pending request (human command). True if one was pending."""
        if self.check_stop_requested("") is None:
            return False
        self.path.unlink()
        return True


def load_stop_controller(config_data: dict[str, Any], run_dir: Path) -> Optional[FileStopController]:
    """The configured stop controller, or None when remote stop is disabled."""
    control = config_data["control"]
    if not control["remote_stop_enabled"]:
        return None
    if control["provider"] != "file":  # rejected by preflight; never silently ignore a configured stop channel
        raise ValueError(f"control.provider {control['provider']!r} is not implemented")
    return FileStopController(run_dir)
