"""Provider adapters: availability, command construction, output parsing (no live calls)."""

import json
import os
from pathlib import Path
from dataclasses import replace

import pytest

from autobuild.providers.adapters.claude import ClaudeAdapter
from autobuild.providers.adapters.claude_hook import decide
from autobuild.providers.adapters.codex import CodexAdapter
from autobuild.providers.agent_provider import AgentRequest
from autobuild.providers.provider_loader import ProviderLoadError, load_adapter
from autobuild.providers.provider_registry import RoleAssignment, resolve_assignments
from autobuild.common.schemas import load_schema
from helpers import starter_config

REPORT = {"implementation_summary": "s", "files_changed": ["a"], "tests_reported": [],
          "documentation_changed": [], "assumptions": [], "known_issues": []}


def _assignment(provider: str, command: str, model=None) -> RoleAssignment:
    return RoleAssignment("implementer", provider, provider.title(), command, model)


def _fake_cli(tmp_path: Path, name: str, exit_code: int = 0) -> str:
    script = tmp_path / name
    script.write_text(f"#!/bin/sh\necho '{name} 9.9.9'\nexit {exit_code}\n")
    script.chmod(0o755)
    return str(script)


def _request(tmp_path: Path, **kwargs) -> AgentRequest:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("do it")
    return AgentRequest(role="implementer", prompt_file=prompt, working_directory=tmp_path,
                        output_directory=tmp_path / "out", report_schema=load_schema("implementation-report"),
                        session_id="11111111-2222-3333-4444-555555555555", **kwargs)


# --- Availability ---

@pytest.mark.parametrize("adapter_class", [ClaudeAdapter, CodexAdapter])
def test_available_when_cli_runs(tmp_path, adapter_class):
    health = adapter_class(_assignment("x", _fake_cli(tmp_path, "cli"))).health_check()
    assert health.available and health.version == "cli 9.9.9"


@pytest.mark.parametrize("adapter_class", [ClaudeAdapter, CodexAdapter])
def test_unavailable_when_missing_or_broken(tmp_path, adapter_class):
    missing = adapter_class(_assignment("x", "no-such-provider-cli")).health_check()
    assert not missing.available and "not found" in missing.detail
    broken = adapter_class(_assignment("x", _fake_cli(tmp_path, "broken", exit_code=1))).health_check()
    assert not broken.available


def test_registry_loads_real_adapters_and_reports_missing_adapter():
    resolved = resolve_assignments(starter_config())
    assert type(load_adapter(resolved["implementer"])).__name__ == "ClaudeAdapter"
    assert type(load_adapter(resolved["reviewer"])).__name__ == "CodexAdapter"
    with pytest.raises(ProviderLoadError):
        load_adapter(_assignment("ghost", "x"), {"providers": {"ghost": {"adapter": "nope.module:X"}}})


# --- Command construction ---

def test_claude_command(tmp_path):
    command = ClaudeAdapter(_assignment("claude", "claude", model="m1")).build_command(_request(tmp_path))
    assert command[:2] == ["claude", "-p"]
    flags = dict(zip(command[2::2], command[3::2]))
    assert flags["--output-format"] == "json" and flags["--permission-prompts"] == "none"
    assert flags["--permission-mode"] == "acceptEdits" and flags["--model"] == "m1"
    assert flags["--session-id"] == "11111111-2222-3333-4444-555555555555"
    assert "$schema" not in json.loads(flags["--json-schema"])
    hook = json.loads(flags["--settings"])["hooks"]["PreToolUse"][0]
    assert "Bash" in hook["matcher"] and "autobuild.providers.adapters.claude_hook" in hook["hooks"][0]["command"]
    assert "WebFetch" in flags["--disallowedTools"]


def test_codex_command(tmp_path):
    request = _request(tmp_path)
    request.output_directory.mkdir()
    command = CodexAdapter(_assignment("codex", "codex")).build_command(request)
    assert command[:4] == ["codex", "--ask-for-approval", "never", "exec"] and command[-1] == "-"
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert command[command.index("--cd") + 1] == str(tmp_path)
    schema = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
    assert "$schema" not in schema and schema["additionalProperties"] is False


@pytest.mark.parametrize("adapter_class", [ClaudeAdapter, CodexAdapter])
def test_resume_command(tmp_path, adapter_class):
    (tmp_path / "out").mkdir()
    command = adapter_class(_assignment("x", "x")).build_command(_request(tmp_path, resume_session_id="s"))
    flag = "resume" if adapter_class is CodexAdapter else "--resume"
    assert command[command.index(flag) + 1] == "s"
    assert "--session-id" not in command


@pytest.mark.parametrize("adapter_class", [ClaudeAdapter, CodexAdapter])
def test_review_command_is_read_only_and_fresh(tmp_path, adapter_class):
    (tmp_path / "out").mkdir()
    request = replace(_request(tmp_path), role="reviewer", report_schema=load_schema("review"))
    adapter = adapter_class(_assignment("x", "x"))
    command = adapter.build_command(request)
    if adapter_class is CodexAdapter:
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert command[command.index("--ask-for-approval") + 1] == "never"
    else:
        assert command[command.index("--allowedTools") + 1] == "Read,Glob,Grep"
        assert command[command.index("--tools") + 1] == "Read,Glob,Grep"
        assert "Bash" in command[command.index("--disallowedTools") + 1]
        assert command[command.index("--permission-mode") + 1] == "default"
    with pytest.raises(ValueError, match="fresh"):
        adapter.build_command(replace(request, resume_session_id="s"))


@pytest.mark.parametrize("tool", ["Bash", "Edit", "Write", "MultiEdit", "NotebookEdit", "TodoWrite"])
def test_review_hook_refuses_mutations(tmp_path, tool):
    assert decide({"tool_name": tool, "tool_input": {}}, tmp_path, "reviewer")


# --- Output parsing ---

def test_claude_parses_structured_output_and_errors(tmp_path):
    adapter, request = ClaudeAdapter(_assignment("claude", "claude")), _request(tmp_path)
    out = tmp_path / "stdout.json"
    out.write_text(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1",
                               "result": "done", "structured_output": REPORT}))
    assert adapter.parse_output(request, out) == ("s-1", REPORT, None)
    out.write_text(json.dumps({"type": "result", "subtype": "success", "session_id": "s-1",
                               "result": "```json\n" + json.dumps(REPORT) + "\n```"}))
    assert adapter.parse_output(request, out)[1] == REPORT
    out.write_text(json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "session_id": "s-1"}))
    session, report, error = adapter.parse_output(request, out)
    assert session == "s-1" and report is None and "error_max_turns" in error


def test_codex_parses_events_and_last_message(tmp_path):
    adapter, request = CodexAdapter(_assignment("codex", "codex")), _request(tmp_path)
    request.output_directory.mkdir()
    events = tmp_path / "events.jsonl"
    events.write_text('{"type":"thread.started","thread_id":"th-9"}\nnot json\n{"type":"turn.completed"}\n')
    (request.output_directory / "codex-last-message.txt").write_text(json.dumps(REPORT))
    assert adapter.parse_output(request, events) == ("th-9", REPORT, None)
    (request.output_directory / "codex-last-message.txt").write_text(json.dumps({"implementation_summary": 1}))
    _, report, error = adapter.parse_output(request, events)
    assert report is None and "does not match schema" in error


def test_codex_projects_review_shape_but_validates_full_contract(tmp_path):
    request = replace(_request(tmp_path), role="reviewer", report_schema=load_schema("review"))
    request.output_directory.mkdir()
    adapter = CodexAdapter(_assignment("codex", "codex"))
    command = adapter.build_command(request)
    wire = json.loads(Path(command[command.index("--output-schema") + 1]).read_text())
    assert "allOf" not in wire and "allOf" not in wire["properties"]["evidence_reviewed"]
    assert set(wire["required"]) == set(wire["properties"])
    review = {"schema_version": 1, "run_id": "run", "implementation_id": "id", "cycle": 1,
              "status": "PASS", "reviewer": {"provider": "codex", "session_id": "s"},
              "reviewed_at": "2026-10-04T00:00:00Z", "evidence_reviewed": ["brief", "git_diff"],
              "findings": [], "blocked_reason": None}
    last = request.output_directory / "codex-last-message.txt"
    last.write_text(json.dumps(review))
    events = tmp_path / "events"
    events.write_text('{"thread_id":"s"}\n')
    assert "blocked_reason" not in adapter.parse_output(request, events)[1]
    review["status"] = "REVISE"
    last.write_text(json.dumps(review))
    assert adapter.parse_output(request, events)[1] is None


# --- Claude pre-tool hook ---

def test_claude_hook_decisions(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    assert decide({"tool_name": "Bash", "tool_input": {"command": "pytest -q && git status"}}, wt) is None
    assert decide({"tool_name": "Bash", "tool_input": {"command": "cd x && git push origin main"}}, wt)
    assert decide({"tool_name": "Bash", "tool_input": {"command": "FOO=1 /usr/bin/git checkout main"}}, wt)
    assert decide({"tool_name": "Write", "tool_input": {"file_path": str(wt / "a.txt")}}, wt) is None
    assert decide({"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "outside.txt")}}, wt)
    assert decide({"tool_name": "Write", "tool_input": {"file_path": ".git"}}, wt)
    assert decide({"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}, wt) is None
