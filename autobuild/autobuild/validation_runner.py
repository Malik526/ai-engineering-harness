"""Controller-owned validation: run the project's configured commands in the worktree.

These results are the only authoritative validation evidence. Commands come
from the human-owned project config, never from an agent.
"""

import fnmatch
import os
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

_DEFAULT_TIMEOUT_SECONDS = 1800
_SHELL_BUILTINS = {
    "cd", "export", "test", "[", "true", "false", "echo", "printf", "set", "unset", ":", "source", ".",
    "exit", "eval", "exec", "command", "type", "umask", "ulimit", "wait", "read", "if", "for", "while", "case", "{", "(",
}
_FAILING = ("failed", "timed_out", "error")


@dataclass(frozen=True)
class ValidationOutcome:
    document: dict[str, Any]  # validation.schema.json
    failed_required: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failed_required


def substitute(text: str, project_root: Path, worktree: Path) -> str:
    return text.replace("${PROJECT_ROOT}", str(project_root)).replace("${WORKTREE}", str(worktree))


def command_unavailable(spec: dict[str, Any], project_root: Path) -> Optional[str]:
    """Reason the command's program cannot be found before the run starts, or None."""
    run = spec["run"].replace("${PROJECT_ROOT}", str(project_root))
    try:
        words = shlex.split(run)
    except ValueError as exc:
        return f"validation.{spec['name']}: cannot parse command: {exc}"
    while words and "=" in words[0] and not words[0].startswith(("/", ".")):
        words = words[1:]  # VAR=value prefixes
    if not words or words[0] in _SHELL_BUILTINS or "${WORKTREE}" in words[0]:
        return None
    program = words[0]
    if "/" in program:
        return None if os.access(program, os.X_OK) else f"validation.{spec['name']}: {program} is not executable"
    return None if shutil.which(program) else f"validation.{spec['name']}: {program!r} not found on PATH"


def _applies(spec: dict[str, Any], changed_files: Sequence[str]) -> bool:
    patterns = spec.get("paths")
    return not patterns or any(fnmatch.fnmatch(f, p) for f in changed_files for p in patterns)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_one(spec: dict[str, Any], index: int, project_root: Path, worktree: Path,
             run_dir: Path, logs_dir: Path) -> dict[str, Any]:
    command = substitute(spec["run"], project_root, worktree)
    cwd = worktree / spec["cwd"] if spec.get("cwd") else worktree
    stdout_path = logs_dir / f"{index:02d}-{spec['name']}.stdout.log"
    stderr_path = logs_dir / f"{index:02d}-{spec['name']}.stderr.log"
    record: dict[str, Any] = {
        "name": spec["name"], "kind": spec["kind"], "command": command,
        "cwd": str(cwd.relative_to(worktree)) if cwd != worktree else ".",
        "required": spec.get("required", True), "started_at": _now(),
        "stdout_path": str(stdout_path.relative_to(run_dir)), "stderr_path": str(stderr_path.relative_to(run_dir)),
    }
    if not cwd.is_dir():
        return {**record, "exit_code": None, "status": "error", "duration_seconds": 0, "detail": f"cwd {cwd} does not exist"}
    env = {**os.environ, **{k: substitute(v, project_root, worktree) for k, v in spec.get("env", {}).items()}}
    started = time.monotonic()
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        process = subprocess.Popen(["/bin/sh", "-c", command], cwd=cwd, env=env, stdout=out, stderr=err,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            exit_code: Optional[int] = process.wait(timeout=spec.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS))
            status = "passed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            exit_code, status = None, "timed_out"
    return {**record, "exit_code": exit_code, "status": status, "duration_seconds": round(time.monotonic() - started, 3)}


def run_validation(*, run_id: str, commands: Sequence[dict[str, Any]], project_root: Path, worktree: Path,
                   changed_files: Sequence[str], run_dir: Path,
                   logs_subdirectory: str = "validation/logs") -> ValidationOutcome:
    """Run every command in order (all of them, so one failure does not hide others)."""
    logs_dir = run_dir / logs_subdirectory
    logs_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for index, spec in enumerate(commands, start=1):
        if not _applies(spec, changed_files):
            results.append({
                "name": spec["name"], "kind": spec["kind"], "command": substitute(spec["run"], project_root, worktree),
                "required": spec.get("required", True), "exit_code": None, "status": "skipped",
                "started_at": _now(), "duration_seconds": 0, "detail": "no changed file matches its paths filter",
            })
            continue
        results.append(_run_one(spec, index, project_root, worktree, run_dir, logs_dir))
    failed = tuple(r["name"] for r in results if r["required"] and r["status"] in _FAILING)
    document = {"schema_version": 1, "run_id": run_id, "producer": "controller", "commands": results}
    return ValidationOutcome(document=document, failed_required=failed)
