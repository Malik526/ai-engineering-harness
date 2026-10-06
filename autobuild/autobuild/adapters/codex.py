"""Codex adapter: `codex exec` in the workspace-write sandbox with an output schema.

The sandbox confines file writes to the worktree (plus temp dirs) and blocks
network access, so the agent cannot write the main repository's refs or push.
The controller's git shim on PATH and protected-ref verification apply as well.
Failure kinds come from Codex's own top-level error events and stderr, never
from the agent's messages.
"""

import json
from pathlib import Path
from typing import Optional

from autobuild.agent_provider import AgentRequest
from autobuild.structured_output import parse_report, validate_report
from autobuild.adapters.codex_schema import output_schema, omit_optional_nulls
from autobuild.provider_failures import (PROVIDER_HARD_LIMIT, PROVIDER_UNAVAILABLE, QUOTA_EXHAUSTED, SCHEMA_REJECTED,
                                         SESSION_EXHAUSTED, SESSION_UNAVAILABLE, TRANSIENT)
from autobuild.subprocess_adapter import SubprocessAdapter

_SESSION_KEYS = ("thread_id", "session_id", "conversation_id")
# Ordered: the most specific match wins. Observed with Codex CLI 0.160.0:
# usage limit -> `error`/`turn.failed` events; unknown resume id -> stderr
# "thread/resume failed: no rollout found for thread id".
_FAILURE_PATTERNS = [
    (SCHEMA_REJECTED, r"invalid_json_schema|invalid schema for response_format|output.?schema.{0,40}invalid"),
    (SESSION_UNAVAILABLE, r"no rollout found for thread id|thread/resume failed|thread .{0,80} not found"),
    (SESSION_EXHAUSTED, r"context_length_exceeded|context window|exceeds the context"),
    (QUOTA_EXHAUSTED, r"hit your usage limit|usage limit|insufficient_quota|quota exceeded|purchase more credits"),
    (PROVIDER_HARD_LIMIT, r"billing_hard_limit|account (is )?(suspended|deactivated)"),
    (PROVIDER_UNAVAILABLE, r"\b401\b|unauthorized|not logged in|please (log|sign) ?in|invalid_api_key"),
    (TRANSIENT, r"\b429\b|rate.?limit|stream disconnected|\b5\d\d\b|overloaded|connection (reset|refused)|timed? ?out"),
]


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
        if not text or not text.strip():
            error = "agent produced no final message" + (f"; provider error: {error_event}" if error_event else "")
            return session_id, None, error
        try:
            value = json.loads(text) if text else None
        except json.JSONDecodeError:
            report, error = parse_report(text, request.report_schema)
        else:
            report, error = validate_report(omit_optional_nulls(value, request.report_schema), request.report_schema)
        if report is None and error_event:
            error = f"{error}; provider error: {error_event}"
        return session_id, report, error

    reports_usage = True

    def parse_usage(self, request: AgentRequest) -> Optional[dict]:
        """Sum of `turn.completed` usage; Codex's input_tokens already include cached input."""
        path, found, input_tokens, output_tokens = self._stdout_file(request), False, 0, 0
        if not path.exists():
            return None
        for line in path.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            usage = event.get("usage") if isinstance(event, dict) and event.get("type") == "turn.completed" else None
            if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int) and isinstance(usage.get("output_tokens"), int):
                found, input_tokens, output_tokens = True, input_tokens + usage["input_tokens"], output_tokens + usage["output_tokens"]
        return {"input_tokens": input_tokens, "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens} if found else None

    def failure_patterns(self) -> list[tuple[str, str]]:
        return _FAILURE_PATTERNS

    def provider_error_text(self, request: AgentRequest, exit_code: Optional[int]) -> str:
        events = _error_events(self._stdout_file(request))
        return "\n".join(events + [super().provider_error_text(request, exit_code)]).strip()

    @staticmethod
    def _last_message_file(request: AgentRequest) -> Path:
        return request.output_directory / "codex-last-message.txt"


def _error_events(path: Path) -> list[str]:
    """Messages of top-level error/turn.failed events (item-level config warnings are not failures)."""
    if not path.exists():
        return []
    messages = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("type") in ("error", "turn.failed"):
            detail = event.get("message") or event.get("error")
            if isinstance(detail, dict):
                detail = detail.get("message") or json.dumps(detail)
            if detail:
                messages.append(str(detail))
    return messages


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
