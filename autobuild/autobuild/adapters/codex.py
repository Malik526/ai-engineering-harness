"""Codex adapter: `codex exec` in the workspace-write sandbox with an output schema.

The sandbox confines file writes to the worktree (plus temp dirs) and blocks
network access, so the agent cannot write the main repository's refs or push.
The controller's git shim on PATH and protected-ref verification apply as well.
"""

import json
from pathlib import Path
from typing import Optional

from autobuild.agent_provider import AgentRequest
from autobuild.structured_output import parse_report, validate_report
from autobuild.adapters.codex_schema import output_schema, omit_optional_nulls
from autobuild.subprocess_adapter import SubprocessAdapter

_SESSION_KEYS = ("thread_id", "session_id", "conversation_id")


class CodexAdapter(SubprocessAdapter):
    def build_command(self, request: AgentRequest) -> list[str]:
        if request.role == "reviewer" and request.resume_session_id:
            raise ValueError("reviewers must start fresh sessions")
        schema_file = request.output_directory / "codex-report-schema.json"
        schema_file.write_text(json.dumps(output_schema(request.report_schema), indent=2))
        command = [
            self.assignment.command, "--ask-for-approval", "never", "exec",
            "--json",
            "--sandbox", "read-only" if request.role == "reviewer" else "workspace-write",
            "--cd", str(request.working_directory),
        ]
        if request.resume_session_id:
            command += ["resume", request.resume_session_id]
        command += [
            "--output-schema", str(schema_file),
            "--output-last-message", str(self._last_message_file(request)),
        ]
        model = request.model or self.assignment.model
        if model:
            command += ["--model", model]
        return command + ["-"]  # prompt on stdin

    def parse_output(self, request: AgentRequest, stdout_file: Path) -> tuple[Optional[str], Optional[dict], Optional[str]]:
        session_id, error_event = _scan_events(stdout_file)
        last_message = self._last_message_file(request)
        text = last_message.read_text(errors="replace") if last_message.exists() else None
        try:
            value = json.loads(text) if text else None
        except json.JSONDecodeError:
            report, error = parse_report(text, request.report_schema)
        else:
            report, error = validate_report(omit_optional_nulls(value, request.report_schema), request.report_schema)
        if report is None and error_event:
            error = f"{error}; provider error: {error_event}"
        return session_id, report, error

    @staticmethod
    def _last_message_file(request: AgentRequest) -> Path:
        return request.output_directory / "codex-last-message.txt"


def _scan_events(path: Path) -> tuple[Optional[str], Optional[str]]:
    """First session id and last error message found in the JSONL event stream."""
    session_id, error = None, None
    if not path.exists():
        return None, None
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if session_id is None:
            session_id = next((event[k] for k in _SESSION_KEYS if isinstance(event.get(k), str)), None)
        if event.get("type") in ("error", "turn.failed"):
            detail = event.get("message") or event.get("error")
            error = json.dumps(detail) if not isinstance(detail, str) else detail
    return session_id, error
