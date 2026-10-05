"""Controller-owned deterministic browser execution and immutable attempt evidence."""

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

from autobuild.browser_artifacts import collect, file_record
from autobuild.browser_sandbox import isolated_environment, sandbox_command
from autobuild.browser_worker import terminate
from autobuild.command_guard import is_within
from autobuild.run_store import utc_now
from autobuild.schemas import schema_errors


def approved_cwd(worktree: Path, relative: str) -> Path:
    path = worktree / relative
    if not is_within(path, worktree) or not path.is_dir():
        raise ValueError("browser cwd must be an existing directory inside the worktree")
    return path.resolve()


def run_browser(*, run_id, attempt, review_cycle, worktree, head_commit, snapshot_tree,
                brief_sha256, config, run_dir, browser_required=False):
    gates = list(config["validation"].get("browser_gates", []))
    if not gates and not browser_required:
        return None
    if browser_required and not any(g.get("required", True) and g.get("enabled", True) for g in gates):
        gates.append({"id": "missing-browser-coverage", "kind": "browser", "command": [],
                      "required": True, "enabled": False})
    cycle_dir = run_dir / f"browser/cycle-{attempt:02d}"
    cycle_dir.mkdir(parents=True, exist_ok=False)
    started = utc_now()
    records, files = [], []
    for gate in gates:
        directory = cycle_dir / gate["id"]
        directory.mkdir()
        begin, tick = utc_now(), time.monotonic()
        status, code, detail, artifacts = "SKIPPED", None, "gate explicitly disabled", []
        if gate["id"] == "missing-browser-coverage":
            detail = "brief requires browser evidence but no enabled required gate is configured"
        environment = {}
        cwd = str(worktree / gate.get("cwd", "."))
        service_cwd = str(worktree / gate.get("service", {}).get("cwd", gate.get("cwd", ".")))
        with tempfile.TemporaryDirectory(prefix="autobuild-browser-") as temporary:
            inputs = Path(temporary)
            writable = inputs / "work"
            writable.mkdir()
            (writable / "outputs").mkdir()
            (writable / "home").mkdir()
            environment = isolated_environment(writable, gate.get("env", {}))
            if gate.get("enabled", True):
                process = None
                try:
                    cwd = str(approved_cwd(worktree, gate.get("cwd", ".")))
                    service_cwd = str(approved_cwd(worktree, gate.get("service", {}).get("cwd", gate.get("cwd", "."))))
                    request = {"root": str(writable), "gate": gate, "cwd": cwd, "service_cwd": service_cwd}
                    (inputs / "request.json").write_text(json.dumps(request))
                    command = sandbox_command(worktree, inputs, writable, environment)
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                               start_new_session=True, env={"PATH": "/usr/bin:/bin"})
                    raw, errors = process.communicate(timeout=gate.get("timeout_seconds", 180)
                                                     + gate.get("service", {}).get("timeout_seconds", 60) + 10)
                    if process.returncode != 0:
                        raise RuntimeError("browser sandbox/worker failed: " + errors.decode(errors="replace")[-2048:])
                    result = json.loads(raw)
                    status, code, detail = result["status"], result["exit_code"], result["detail"]
                    if (status not in ("PASS", "FAIL", "ERROR") or not isinstance(detail, str)
                            or (code is not None and (not isinstance(code, int) or isinstance(code, bool)))
                            or (status == "PASS" and code != 0) or (status == "FAIL" and code in (0, None))):
                        raise ValueError("invalid controller worker result")
                    artifacts = collect(writable / "outputs", directory / "artifacts", gate.get("artifacts", []), run_dir)
                except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    status, detail = "ERROR", f"{type(exc).__name__}: {exc}"
                finally:
                    terminate(process)
            for name in ("stdout.txt", "stderr.txt", "service.stdout.txt", "service.stderr.txt"):
                source = writable / name
                target = directory / name
                try:
                    if source.exists() or source.is_symlink():
                        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        with os.fdopen(descriptor, "rb") as stream:
                            metadata = os.fstat(stream.fileno())
                            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > 64 * 1024 * 1024:
                                raise ValueError("unsafe or oversized browser log")
                            target.write_bytes(stream.read())
                    else:
                        target.write_text("")
                except (OSError, ValueError) as exc:
                    status, detail = "ERROR", f"unsafe browser log: {exc}"
                    target.write_text("")
                files.append(file_record(target, run_dir))
            summaries = {}
            for name in ("stdout", "stderr"):
                with (directory / f"{name}.txt").open("rb") as stream:
                    summaries[name] = stream.read(8192).decode(errors="replace")[:2048]
            record = {"id": gate["id"], "kind": gate["kind"], "required": gate.get("required", True),
                      "command": gate["command"], "cwd": cwd, "timeout_seconds": gate.get("timeout_seconds", 180),
                      "expected_exit_code": 0, "environment": {"policy": "isolated-explicit", "keys": sorted(environment),
                      "sha256": hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest()},
                      "status": status, "exit_code": code, "started_at": begin, "finished_at": utc_now(),
                      "duration_seconds": round(time.monotonic() - tick, 3), "detail": detail,
                      "stdout_path": (directory / "stdout.txt").relative_to(run_dir).as_posix(),
                      "stderr_path": (directory / "stderr.txt").relative_to(run_dir).as_posix(),
                      "stdout_summary": summaries["stdout"], "stderr_summary": summaries["stderr"], "artifacts": artifacts}
            if gate.get("service"):
                record["service"] = {"command": gate["service"]["command"], "cwd": service_cwd,
                                     "ready_url": gate["service"]["ready_url"],
                                     "timeout_seconds": gate["service"].get("timeout_seconds", 60)}
            evidence = directory / "evidence.json"
            evidence.write_text(json.dumps(record, indent=2) + "\n")
            records.append(record)
            files += [file_record(evidence, run_dir), *artifacts]
    document = {"schema_version": 1, "producer": "controller", "run_id": run_id, "attempt": attempt,
                "review_cycle": review_cycle, "worktree": str(worktree), "head_commit": head_commit,
                "snapshot_tree": snapshot_tree, "brief_sha256": brief_sha256,
                "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                "started_at": started, "finished_at": utc_now(), "gates": records, "files": files,
                "passed": all(g["status"] == "PASS" for g in records if g["required"])}
    errors = schema_errors("browser", document)
    if errors:
        raise RuntimeError("invalid controller browser evidence: " + "; ".join(errors))
    (cycle_dir / "results.json").write_text(json.dumps(document, indent=2) + "\n")
    return document
