"""Claude Code adapter: `claude -p` with JSON output and a schema-validated final report.

Confinement (Claude Code's own sandbox needs bubblewrap, which may be absent):
- acceptEdits + --permission-prompts none: file edits run, anything that would
  prompt is denied, nothing waits for a human.
- a PreToolUse hook (claude_hook.py) that refuses edits outside the worktree
  and git commands outside the allowlist;
- web tools disabled.
The controller's git shim on PATH and protected-ref verification apply as well.

Structured output: the canonical report schema is projected by claude_schema.py
(Claude's API rejects top-level combinators) and the answer is validated against
the unchanged canonical schema. Failure kinds come from Claude's own error text.
"""

import json
import shlex
import sys
from pathlib import Path
from typing import Optional

from autobuild.providers.agent_provider import AgentRequest
from autobuild.common.paths import CORE_ROOT
from autobuild.providers.adapters.claude_schema import input_schema
from autobuild.providers.provider_failures import (PROVIDER_HARD_LIMIT, PROVIDER_UNAVAILABLE, QUOTA_EXHAUSTED, SCHEMA_REJECTED,
                                         SESSION_EXHAUSTED, SESSION_UNAVAILABLE, TRANSIENT)
from autobuild.providers.structured_output import parse_report, validate_report
from autobuild.providers.subprocess_adapter import SubprocessAdapter

_ALLOWED_TOOLS = "Bash,Read,Edit,MultiEdit,Write,Glob,Grep,TodoWrite,NotebookEdit"
_DISALLOWED_TOOLS = "WebFetch,WebSearch"
_HOOK_MATCHER = "Bash|Edit|MultiEdit|Write|NotebookEdit"
# Ordered: the most specific match wins. Matched only against provider error text.
_FAILURE_PATTERNS = [
    (SCHEMA_REJECTED, r"API Error: 400\b.*(input_schema|json[_ ]schema|output_format)"),
    (SESSION_UNAVAILABLE, r"No conversation found with session ID|session .{0,80} (not found|does not exist)"),
    (SESSION_EXHAUSTED, r"prompt is too long|context (window|length) (exceeded|limit)|conversation is too long"),
    (QUOTA_EXHAUSTED, r"usage limit|hit your (usage )?limit|(5-hour|weekly|session|opus|usage) limit (reached|exceeded)"),
    (PROVIDER_HARD_LIMIT, r"credit balance is too low|out of extra usage|billing"),
    (PROVIDER_UNAVAILABLE, r"API Error: 40[13]\b|invalid api key|please run /login|not logged in|authentication_error"),
    (TRANSIENT, r"API Error: (429|5\d\d)\b|overloaded|rate.?limit|ECONNRESET|socket hang up|fetch failed|network error"),
]


def hook_command() -> str:
    return f"PYTHONPATH={shlex.quote(str(CORE_ROOT))} {shlex.quote(sys.executable)} -m autobuild.providers.adapters.claude_hook"


class ClaudeAdapter(SubprocessAdapter):
    def build_command(self, request: AgentRequest) -> list[str]:
        reviewer = request.role == "reviewer"
        if reviewer and request.resume_session_id:
            raise ValueError("reviewers must start fresh sessions")
        settings = {"hooks": {"PreToolUse": [
            {"matcher": _HOOK_MATCHER, "hooks": [{"type": "command", "command": hook_command()}]}
        ]}}
        command = [
            self.assignment.command, "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(input_schema(request.report_schema)),
            "--permission-mode", "default" if reviewer else "acceptEdits",
            "--permission-prompts", "none",
            "--allowedTools", "Read,Glob,Grep" if reviewer else _ALLOWED_TOOLS,
            "--disallowedTools", _DISALLOWED_TOOLS + (",Bash,Edit,MultiEdit,Write,NotebookEdit,TodoWrite" if reviewer else ""),
            "--settings", json.dumps(settings),
        ]
        if reviewer:
            command += ["--tools", "Read,Glob,Grep"]
        if request.resume_session_id:
            command += ["--resume", request.resume_session_id]
        elif request.session_id:
            command += ["--session-id", request.session_id]
        model = request.model or self.assignment.model
        if model:
            command += ["--model", model]
        return command

    def parse_output(self, request: AgentRequest, stdout_file: Path) -> tuple[Optional[str], Optional[dict], Optional[str]]:
        envelope = _last_json_object(stdout_file)
        if envelope is None:
            return None, None, "no JSON result envelope in provider output"
        session_id = envelope.get("session_id")
        if envelope.get("is_error") or envelope.get("subtype", "success") != "success":
            return session_id, None, f"provider reported {envelope.get('subtype', 'error')}: {str(envelope.get('result', ''))[:500]}"
        if isinstance(envelope.get("structured_output"), dict):
            report, error = validate_report(envelope["structured_output"], request.report_schema)
        else:
            report, error = parse_report(envelope.get("result"), request.report_schema)
        return session_id, report, error


    reports_usage = True

    def parse_usage(self, request: AgentRequest) -> Optional[dict]:
        envelope = _last_json_object(self._stdout_file(request))
        usage = (envelope or {}).get("usage")
        if not isinstance(usage, dict):
            return None
        tokens = [usage.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                                            "output_tokens")]
        if not all(isinstance(t, int) and t >= 0 for t in tokens):
            return None
        record = {"input_tokens": sum(tokens[:3]), "output_tokens": tokens[3], "total_tokens": sum(tokens)}
        if isinstance(envelope.get("total_cost_usd"), (int, float)) and envelope["total_cost_usd"] >= 0:
            record["provider_cost_usd"] = float(envelope["total_cost_usd"])
        return record

    def failure_patterns(self) -> list[tuple[str, str]]:
        return _FAILURE_PATTERNS

    def provider_error_text(self, request: AgentRequest, exit_code: Optional[int]) -> str:
        parts = []
        envelope = _last_json_object(self._stdout_file(request))
        if envelope is not None and (envelope.get("is_error") or envelope.get("subtype", "success") != "success"):
            status = envelope.get("api_error_status")
            parts.append((f"API Error: {status} " if status and "API Error" not in str(envelope.get("result")) else "")
                         + str(envelope.get("result", "")))
        parts.append(super().provider_error_text(request, exit_code))
        return "\n".join(part for part in parts if part)


def _last_json_object(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    text = path.read_text(errors="replace").strip()
    for candidate in [text, *reversed(text.splitlines())]:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None
