"""Controller validation, with fail-closed confinement for every checkpoint-capable run."""

import fnmatch
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import shlex
import stat
import subprocess
import tarfile
import tempfile
import time
from typing import Any, Optional, Sequence

from autobuild.validation.browser_artifacts import file_record
from autobuild.git.command_guard import is_within
from autobuild.common.paths import CORE_ROOT
from autobuild.validation.process_lifecycle import terminate_process_group
from autobuild.validation.sandbox import SandboxPolicy, isolated_environment, sandbox_command
from autobuild.validation.validation_contract import config_digest

_DEFAULT_TIMEOUT_SECONDS = 1800
_FAILING = ("FAIL", "ERROR")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ValidationOutcome:
    def __init__(self, document: dict[str, Any], failed_required: tuple[str, ...], execution_root: Path | None = None,
                 temporary: tempfile.TemporaryDirectory | None = None):
        self.document = document
        self.failed_required = failed_required
        self.execution_root = execution_root
        self._temporary = temporary

    @property
    def passed(self) -> bool:
        return not self.failed_required

    def cleanup(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None


def substitute(text: str, project_root: Path, worktree: Path) -> str:
    return text.replace("${PROJECT_ROOT}", str(project_root)).replace("${WORKTREE}", str(worktree))


def command_argv(spec: dict[str, Any], project_root: Path, worktree: Path) -> tuple[list[str], str]:
    if "command" in spec:
        return [substitute(value, project_root, worktree) for value in spec["command"]], "argv"
    return ["/bin/sh", "-c", substitute(spec["run"], project_root, worktree)], "legacy-shell"


def command_unavailable(spec: dict[str, Any], project_root: Path) -> Optional[str]:
    """Only reject malformed legacy syntax; executable availability is sandbox truth."""
    if "command" in spec:
        return None
    try:
        shlex.split(spec["run"].replace("${PROJECT_ROOT}", str(project_root)))
    except ValueError as exc:
        return f"validation.{spec['name']}: cannot parse command: {exc}"
    return None


def _applies(spec: dict[str, Any], changed_files: Sequence[str]) -> bool:
    patterns = spec.get("paths")
    return not patterns or any(fnmatch.fnmatch(path, pattern) for path in changed_files for pattern in patterns)


def _approved_cwd(root: Path, relative: str) -> Path:
    path = root / relative
    if not is_within(path, root) or not path.is_dir() or any(parent.is_symlink() for parent in (path, *path.parents) if parent != root):
        raise ValueError("validation cwd must be a real directory inside the source snapshot")
    return path.resolve()


def _materialize_snapshot(worktree: Path, snapshot_tree: str, destination: Path) -> None:
    done = subprocess.run(["git", "archive", "--format=tar", snapshot_tree], cwd=worktree,
                          stdin=subprocess.DEVNULL, capture_output=True)
    if done.returncode != 0:
        raise RuntimeError("cannot materialize source snapshot: " + done.stderr.decode(errors="replace")[-2048:])
    with tarfile.open(fileobj=io.BytesIO(done.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            target = destination / member.name
            if not is_within(target, destination) or member.islnk() or member.isdev():
                raise ValueError("source snapshot contains an unsafe archive entry")
            if member.issym():
                link_target = Path(member.linkname)
                if link_target.is_absolute() or ".." in link_target.parts:
                    raise ValueError("source snapshot contains an escaping symlink")
        archive.extractall(destination)


def _copy_log(source: Path, target: Path) -> Optional[str]:
    if not source.exists() and not source.is_symlink():
        target.write_text("")
        return None
    try:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > 64 * 1024 * 1024:
                raise ValueError("unsafe or oversized validation log")
            target.write_bytes(stream.read())
        return None
    except (OSError, ValueError) as exc:
        target.write_text("")
        return f"unsafe validation log: {exc}"


def _summary(path: Path) -> str:
    with path.open("rb") as stream:
        return stream.read(8192).decode(errors="replace")[:2048]


def _run_confined_command(spec: dict[str, Any], index: int, workspace: Path, runtime: Path, inputs: Path,
                          logs_dir: Path, run_dir: Path, bindings: tuple[tuple[Path, Path], ...]) -> tuple[dict, list[dict]]:
    command_root = runtime / f"command-{index:02d}"
    command_root.mkdir()
    argv, contract = command_argv(spec, workspace, workspace)
    explicit = {key: substitute(value, workspace, workspace) for key, value in spec.get("env", {}).items()}
    environment = isolated_environment(runtime, explicit)
    request_path = inputs / f"command-{index:02d}.json"
    stdout_path = logs_dir / f"{index:02d}-{spec['name']}.stdout.log"
    stderr_path = logs_dir / f"{index:02d}-{spec['name']}.stderr.log"
    started_at, started = utc_now(), time.monotonic()
    status, exit_code, detail = "ERROR", None, "sandbox did not complete"
    process = None
    try:
        cwd = _approved_cwd(workspace, spec.get("cwd", "."))
        request = {"root": str(command_root), "argv": argv, "cwd": str(cwd),
                   "timeout_seconds": spec.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)}
        request_path.write_text(json.dumps(request))
        writable_paths = (runtime / "home", runtime / "cache", runtime / "config", runtime / "state",
                          runtime / "scratch", command_root)
        policy = SandboxPolicy(label="normal validation", execution_root=workspace, writable_root=workspace,
                               input_root=inputs, environment=environment, network=spec.get("network", "none"),
                               read_only_paths=(CORE_ROOT / "autobuild/validation/validation_worker.py",),
                               read_only_bindings=bindings, writable_paths=writable_paths)
        command = sandbox_command(policy, [os.sys.executable, "-I", str(CORE_ROOT / "autobuild/validation/validation_worker.py"),
                                           str(request_path)])
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                                   env={"PATH": "/usr/bin:/bin"})
        raw, worker_stderr = process.communicate(timeout=request["timeout_seconds"] + 10)
        if process.returncode != 0:
            raise RuntimeError("validation sandbox/worker failed: " + worker_stderr.decode(errors="replace")[-2048:])
        result = json.loads(raw)
        status, exit_code, detail = result["status"], result["exit_code"], result["detail"]
        if (status not in ("PASS", "FAIL", "ERROR") or not isinstance(detail, str)
                or (exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)))
                or (status == "PASS" and exit_code != 0) or (status == "FAIL" and exit_code in (0, None))):
            raise ValueError("invalid validation worker result")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        detail = f"{type(exc).__name__}: {exc}"
    finally:
        terminate_process_group(process)
    for name, target in (("stdout.txt", stdout_path), ("stderr.txt", stderr_path)):
        problem = _copy_log(command_root / name, target)
        if problem:
            status, detail = "ERROR", problem
    files = [file_record(stdout_path, run_dir), file_record(stderr_path, run_dir)]
    record = {
        "name": spec["name"], "kind": spec["kind"], "argv": argv, "contract": contract,
        "cwd": spec.get("cwd", "."), "required": spec.get("required", True),
        "network": spec.get("network", "none"), "sandbox": "bubblewrap-snapshot-v1",
        "environment": {"policy": "isolated-explicit", "keys": sorted(environment),
                        "sha256": hashlib.sha256(json.dumps(environment, sort_keys=True).encode()).hexdigest()},
        "started_at": started_at, "finished_at": utc_now(),
        "duration_seconds": round(time.monotonic() - started, 3), "exit_code": exit_code, "status": status,
        "detail": detail, "stdout_path": stdout_path.relative_to(run_dir).as_posix(),
        "stderr_path": stderr_path.relative_to(run_dir).as_posix(), "stdout_summary": _summary(stdout_path),
        "stderr_summary": _summary(stderr_path),
    }
    return record, files


def _run_host_compat(spec: dict[str, Any], index: int, project_root: Path, worktree: Path,
                     run_dir: Path, logs_dir: Path) -> dict[str, Any]:
    """Manual-completion compatibility only; Autobuild always supplies a snapshot tree."""
    argv, _ = command_argv(spec, project_root, worktree)
    cwd = worktree / spec.get("cwd", ".")
    stdout_path = logs_dir / f"{index:02d}-{spec['name']}.stdout.log"
    stderr_path = logs_dir / f"{index:02d}-{spec['name']}.stderr.log"
    started_at, started = utc_now(), time.monotonic()
    environment = {**os.environ, **{key: substitute(value, project_root, worktree)
                                    for key, value in spec.get("env", {}).items()}}
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            done = subprocess.run(argv, cwd=cwd, env=environment, stdout=stdout, stderr=stderr,
                                  timeout=spec.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS), stdin=subprocess.DEVNULL)
            code, status, detail = done.returncode, "PASS" if done.returncode == 0 else "FAIL", f"command exited {done.returncode}"
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, status, detail = None, "ERROR", f"{type(exc).__name__}: {exc}"
    return {"name": spec["name"], "kind": spec["kind"], "argv": argv, "contract": "manual-host",
            "cwd": spec.get("cwd", "."), "required": spec.get("required", True), "network": "host",
            "sandbox": "manual-host", "environment": {"policy": "manual", "keys": [], "sha256": "0" * 64},
            "started_at": started_at, "finished_at": utc_now(), "duration_seconds": round(time.monotonic() - started, 3),
            "exit_code": code, "status": status, "detail": detail,
            "stdout_path": stdout_path.relative_to(run_dir).as_posix(), "stderr_path": stderr_path.relative_to(run_dir).as_posix(),
            "stdout_summary": _summary(stdout_path), "stderr_summary": _summary(stderr_path)}


def run_validation(*, run_id: str, commands: Sequence[dict[str, Any]], project_root: Path, worktree: Path,
                   changed_files: Sequence[str], run_dir: Path, logs_subdirectory: str = "validation/logs",
                   snapshot_tree: str | None = None, head_commit: str | None = None, attempt: int = 1,
                   review_cycle: int = 1, brief_sha256: str | None = None, config: dict | None = None,
                   manual_host: bool = False) -> ValidationOutcome:
    """Run all commands confined against `snapshot_tree`; host execution only when `manual_host` asks for it."""
    # Fail closed: a missing snapshot never degrades checkpoint-capable validation to host execution.
    if snapshot_tree is None and not manual_host:
        raise ValueError("checkpoint-capable validation requires a controller source snapshot; "
                         "host execution is reserved for manual completion")
    if snapshot_tree is not None and manual_host:
        raise ValueError("manual host validation cannot claim a controller source snapshot")
    logs_dir = run_dir / logs_subdirectory
    logs_dir.mkdir(parents=True, exist_ok=True)
    if manual_host:
        results = [_run_host_compat(spec, index, project_root, worktree, run_dir, logs_dir)
                   for index, spec in enumerate(commands, 1) if _applies(spec, changed_files)]
        failed = tuple(r["name"] for r in results if r["required"] and r["status"] in _FAILING)
        document = {"schema_version": 2, "run_id": run_id, "producer": "manual", "commands": results,
                    "passed": not failed, "files": []}
        return ValidationOutcome(document, failed)

    temporary = tempfile.TemporaryDirectory(prefix="autobuild-validation-")
    root = Path(temporary.name)
    workspace, runtime, inputs = root / "workspace", root / "runtime", root / "inputs"
    for path in (workspace, runtime, inputs, runtime / "home", runtime / "cache", runtime / "config",
                 runtime / "state", runtime / "scratch"):
        path.mkdir(parents=True, exist_ok=True)
    try:
        _materialize_snapshot(worktree, snapshot_tree, workspace)
        bindings = []
        for relative in (config or {}).get("validation", {}).get("runtime_paths", []):
            source, destination = worktree / relative, workspace / relative
            if not is_within(source, worktree) or source.is_symlink() or not source.exists():
                raise ValueError("validation runtime_path missing or unsafe: " + relative)
            if destination.exists() or destination.is_symlink():
                raise ValueError("validation runtime_path overlaps snapshot content: " + relative)
            destination.mkdir(parents=True)
            bindings.append((source, destination))
        results, files = [], []
        for index, spec in enumerate(commands, 1):
            if not _applies(spec, changed_files):
                argv, contract = command_argv(spec, workspace, workspace)
                results.append({"name": spec["name"], "kind": spec["kind"], "argv": argv, "contract": contract,
                    "cwd": spec.get("cwd", "."), "required": spec.get("required", True),
                    "network": spec.get("network", "none"), "sandbox": "bubblewrap-snapshot-v1",
                    "environment": {"policy": "isolated-explicit", "keys": [], "sha256": hashlib.sha256(b"{}").hexdigest()},
                    "exit_code": None, "status": "SKIPPED", "started_at": utc_now(), "finished_at": utc_now(),
                    "duration_seconds": 0, "detail": "no changed file matches its paths filter",
                    "stdout_path": "", "stderr_path": "", "stdout_summary": "", "stderr_summary": ""})
                continue
            record, command_files = _run_confined_command(spec, index, workspace, runtime, inputs, logs_dir, run_dir,
                                                           tuple(bindings))
            results.append(record)
            files.extend(command_files)
        failed = tuple(r["name"] for r in results if r["required"] and r["status"] in _FAILING)
        document = {"schema_version": 2, "run_id": run_id, "producer": "controller", "attempt": attempt,
                    "review_cycle": review_cycle, "worktree": str(worktree), "head_commit": head_commit,
                    "snapshot_tree": snapshot_tree, "brief_sha256": brief_sha256, "config_sha256": config_digest(config or {}),
                    "started_at": min((r["started_at"] for r in results), default=utc_now()), "finished_at": utc_now(),
                    "passed": not failed, "commands": results, "files": files}
        return ValidationOutcome(document, failed, workspace, temporary)
    except BaseException:
        temporary.cleanup()
        raise
