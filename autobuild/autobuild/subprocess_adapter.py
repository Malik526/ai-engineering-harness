"""Shared machinery for adapters that drive a local CLI as a child process.

Handles what every CLI provider needs — health check, spawning in its own
process group with stdin/stdout/stderr wired to files, timeout, termination —
so concrete adapters only supply their command line and output parsing.
Nothing here is specific to any provider.
"""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import IO, Any, Optional

from autobuild.agent_provider import AgentRequest, AgentResult, ProviderHealth
from autobuild.provider_failures import (INTERRUPTED, INVALID_OUTPUT, TIMEOUT, UNKNOWN, ProviderFailure,
                                         match_failure)
from autobuild.provider_registry import RoleAssignment

_HEALTH_TIMEOUT_SECONDS = 30
_TERMINATE_GRACE_SECONDS = 10


class SubprocessAdapter:
    """Base class: subclasses implement build_command() and parse_output()."""

    def __init__(self, assignment: RoleAssignment):
        self.assignment = assignment
        self.provider_id = assignment.provider
        self._process: Optional[subprocess.Popen] = None
        self._request: Optional[AgentRequest] = None
        self._files: list[IO[Any]] = []
        self._started_at = 0.0
        self._terminated = False

    # --- Subclass API ---

    def version_args(self) -> list[str]:
        return ["--version"]

    def build_command(self, request: AgentRequest) -> list[str]:
        raise NotImplementedError

    def parse_output(self, request: AgentRequest, stdout_file: Path) -> tuple[Optional[str], Optional[dict], Optional[str]]:
        """Return (session_id, structured_output, output_error) from the finished process's output."""
        raise NotImplementedError

    # True when this CLI reports token usage the controller can account (needed for limits.max_usage_tokens).
    reports_usage = False

    def parse_usage(self, request: AgentRequest) -> Optional[dict[str, Any]]:
        """Normalized provider-reported usage: input (including cached) and output tokens. None if absent."""
        return None

    def failure_patterns(self) -> list[tuple[str, str]]:
        """Ordered (failure kind, regex) pairs for this CLI's own error messages."""
        return []

    def provider_error_text(self, request: AgentRequest, exit_code: Optional[int]) -> str:
        """Error text emitted by the provider itself (never the agent's answer). Default: stderr of a failed process."""
        stderr = self._stderr_file(request)
        if exit_code in (0, None) or not stderr.exists():
            return ""
        return stderr.read_text(errors="replace")[-20000:]

    def classify_failure(self, request: AgentRequest, *, exit_code: Optional[int], timed_out: bool,
                         terminated: bool, structured: Optional[dict]) -> Optional[ProviderFailure]:
        """None on success; otherwise the most specific failure kind the evidence supports."""
        if timed_out:
            return ProviderFailure(TIMEOUT, f"exceeded {request.timeout_seconds}s")
        if terminated:
            return ProviderFailure(INTERRUPTED, "terminated by the controller")
        text = self.provider_error_text(request, exit_code)
        if exit_code == 0 and structured is not None and not text:
            return None
        matched = match_failure(text, self.failure_patterns()) if text else None
        if matched:
            return matched
        if exit_code == 0 and not text:
            return ProviderFailure(INVALID_OUTPUT, "the agent's final answer did not satisfy its report schema")
        return ProviderFailure(UNKNOWN, (text.strip().splitlines() or [f"exit code {exit_code}"])[-1][:500])

    # --- AgentProvider ---

    def health_check(self) -> ProviderHealth:
        executable = shutil.which(self.assignment.command)
        if executable is None:
            return ProviderHealth(self.provider_id, False, None, f"executable {self.assignment.command!r} not found on PATH")
        try:
            done = subprocess.run([executable, *self.version_args()], capture_output=True, text=True,
                                  timeout=_HEALTH_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProviderHealth(self.provider_id, False, None, f"{executable} {' '.join(self.version_args())} failed: {exc}")
        output = (done.stdout or done.stderr).strip().splitlines()
        version = output[-1] if output else None
        if done.returncode != 0:
            return ProviderHealth(self.provider_id, False, version, f"{executable} exited {done.returncode}")
        return ProviderHealth(self.provider_id, True, version, executable)

    def start(self, request: AgentRequest) -> None:
        if self._process is not None and self._process.poll() is None:
            raise RuntimeError("adapter already started")
        self._terminated = False
        request.output_directory.mkdir(parents=True, exist_ok=True)
        self._request = request
        command = self.build_command(request)
        stdin = request.prompt_file.open("rb")
        stdout = self._stdout_file(request).open("wb")
        stderr = self._stderr_file(request).open("wb")
        self._files = [stdin, stdout, stderr]
        self._started_at = time.monotonic()
        # Own process group so terminate() reaches every child the agent spawned.
        try:
            self._process = subprocess.Popen(
                command, cwd=request.working_directory, stdin=stdin, stdout=stdout, stderr=stderr,
                env={**os.environ, **request.env}, start_new_session=True,
            )
        except OSError:
            for handle in self._files:
                handle.close()
            raise

    def get_result(self) -> AgentResult:
        if self._process is None or self._request is None:
            raise RuntimeError("adapter not started")
        request = self._request
        timed_out = False
        try:
            self._process.wait(timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            self.terminate()
        finally:
            for handle in self._files:
                handle.close()
        duration = round(time.monotonic() - self._started_at, 3)
        exit_code = self._process.returncode
        session_id, structured, error = self.parse_output(request, self._stdout_file(request))
        failure = self.classify_failure(request, exit_code=None if self._terminated else exit_code,
                                        timed_out=timed_out, terminated=self._terminated, structured=structured)
        return AgentResult(
            provider=self.provider_id,
            session_id=session_id or request.session_id,
            exit_code=None if self._terminated else exit_code,
            timed_out=timed_out,
            terminated=self._terminated,
            duration_seconds=duration,
            stdout_file=self._stdout_file(request),
            stderr_file=self._stderr_file(request),
            structured_output=structured,
            output_error=error,
            failure=failure,
            usage=self.parse_usage(request),
        )

    def terminate(self) -> None:
        for handle in self._files:
            handle.close()
        process = self._process
        if process is None or process.poll() is not None:
            return
        self._terminated = True
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=_TERMINATE_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            pass

    # --- Helpers ---

    @staticmethod
    def _stdout_file(request: AgentRequest) -> Path:
        return request.output_directory / "provider.log"

    @staticmethod
    def _stderr_file(request: AgentRequest) -> Path:
        return request.output_directory / "provider.stderr.log"
