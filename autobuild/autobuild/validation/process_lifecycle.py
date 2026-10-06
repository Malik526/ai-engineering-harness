"""Controller-owned process-group lifecycle shared by validation and browser runners."""

import os
import signal
import subprocess
from typing import Optional


def terminate_process_group(process: Optional[subprocess.Popen], grace_seconds: float = 2) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=grace_seconds)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
