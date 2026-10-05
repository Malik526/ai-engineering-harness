"""Claude Code adapter: `claude -p` with JSON output and a schema-validated final report.

Confinement (Claude Code's own sandbox needs bubblewrap, which may be absent):
- acceptEdits + --permission-prompts none: file edits run, anything that would
  prompt is denied, nothing waits for a human.
- a PreToolUse hook (claude_hook.py) that refuses edits outside the worktree
  and git commands outside the allowlist;
- web tools disabled.
The controller's git shim on PATH and protected-ref verification apply as well.
"""

import json
import shlex
import sys
from pathlib import Path
from typing import Optional

from autobuild.agent_provider import AgentRequest
from autobuild.paths import CORE_ROOT
from autobuild.structured_output import parse_report, strict_schema, validate_report
from autobuild.subprocess_adapter import SubprocessAdapter

_ALLOWED_TOOLS = "Bash,Read,Edit,MultiEdit,Write,Glob,Grep,TodoWrite,NotebookEdit"
_DISALLOWED_TOOLS = "WebFetch,WebSearch"
_HOOK_MATCHER = "Bash|Edit|MultiEdit|Write|NotebookEdit"


def hook_command() -> str:
    return f"PYTHONPATH={shlex.quote(str(CORE_ROOT))} {shlex.quote(sys.executable)} -m autobuild.adapters.claude_hook"


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
            "--json-schema", json.dumps(strict_schema(request.report_schema)),
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
