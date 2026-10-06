"""Controller worker inside a private browser namespace (standard library only)."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def terminate(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def execute(request):
    import resource
    root = Path(request["root"])
    gate = request["gate"]
    service = test = None
    result = {"status": "ERROR", "exit_code": None, "detail": "worker did not complete"}
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    try:
        with (root / "stdout.txt").open("wb") as stdout, (root / "stderr.txt").open("wb") as stderr, \
                (root / "service.stdout.txt").open("wb") as service_out, \
                (root / "service.stderr.txt").open("wb") as service_err:
            if gate.get("service"):
                specification = gate["service"]
                service = subprocess.Popen(specification["command"], cwd=request["service_cwd"],
                                           stdout=service_out, stderr=service_err, start_new_session=True)
                deadline = time.monotonic() + specification.get("timeout_seconds", 60)
                opener = build_opener(ProxyHandler({}), NoRedirect())
                while True:
                    if service.poll() is not None:
                        raise RuntimeError("service exited before readiness")
                    try:
                        with opener.open(specification["ready_url"], timeout=0.5) as response:
                            ready = 200 <= response.status < 300
                    except OSError:
                        ready = False
                    if ready:
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("service readiness timeout")
                    time.sleep(0.1)
            test = subprocess.Popen(gate["command"], cwd=request["cwd"], stdout=stdout, stderr=stderr,
                                    start_new_session=True)
            code = test.wait(timeout=gate.get("timeout_seconds", 180))
            result = {"status": "PASS" if code == 0 else "FAIL", "exit_code": code,
                      "detail": "command exited " + str(code)}
            if service is not None and service.poll() is not None:
                result.update(status="ERROR", detail="service exited during test")
    except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
        result.update(detail=f"{type(exc).__name__}: {exc}")
    finally:
        terminate(test)
        terminate(service)
    return result


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    request = json.loads(Path(sys.argv[1]).read_text())
    print(json.dumps(execute(request)), flush=True)


if __name__ == "__main__":
    main()
