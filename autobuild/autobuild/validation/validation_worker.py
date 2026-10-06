"""Execute one validation argv inside its namespace and own all child cleanup."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys


def terminate(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def execute(request):
    import resource
    root, process = Path(request["root"]), None
    result = {"status": "ERROR", "exit_code": None, "detail": "worker did not complete"}
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    try:
        with (root / "stdout.txt").open("wb") as stdout, (root / "stderr.txt").open("wb") as stderr:
            process = subprocess.Popen(request["argv"], cwd=request["cwd"], stdout=stdout, stderr=stderr,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            code = process.wait(timeout=request["timeout_seconds"])
            result = {"status": "PASS" if code == 0 else "FAIL", "exit_code": code,
                      "detail": "command exited " + str(code)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.update(detail=f"{type(exc).__name__}: {exc}")
    finally:
        terminate(process)
    return result


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    request = json.loads(Path(sys.argv[1]).read_text())
    print(json.dumps(execute(request)), flush=True)


if __name__ == "__main__":
    main()
