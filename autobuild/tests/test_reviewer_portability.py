"""One canonical reviewer contract across providers: wire projections, normalization, failure classification."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from autobuild.adapters.claude import ClaudeAdapter
from autobuild.adapters.claude_schema import SchemaProjectionError, input_schema
from autobuild.adapters.codex import CodexAdapter
from autobuild.adapters.codex_schema import omit_optional_nulls, output_schema
from autobuild.agent_provider import AgentRequest
from autobuild.preflight import preflight
from autobuild.provider_failures import QUOTA_EXHAUSTED, SCHEMA_REJECTED, SESSION_UNAVAILABLE, INVALID_OUTPUT
from autobuild.provider_registry import RoleAssignment
from autobuild.review_contract import normalize_review
from autobuild.runner import Runner
from autobuild.schemas import load_schema
from project_fixture import make_project

SAMPLES = Path(__file__).with_name("provider_samples")
CANONICAL = load_schema("review")
COMBINATORS = {"allOf", "anyOf", "oneOf", "not", "if", "then", "else"}
IDENTITY = {"run_id": "2026-10-05-T-1", "implementation_id": "T-1", "cycle": 1}
REPORT = {"implementation_summary": "s", "files_changed": ["a"], "tests_reported": [],
          "documentation_changed": [], "assumptions": [], "known_issues": []}


def review(status: str) -> dict:
    document = {"schema_version": 1, **IDENTITY, "status": status,
                "reviewer": {"provider": "anything", "session_id": "claimed"}, "reviewed_at": "2026-10-05T05:00:00Z",
                "evidence_reviewed": ["brief", "git_diff", "changed_files", "validation_output"], "findings": []}
    if status == "REVISE":
        document["findings"] = [{"id": "R1-1", "severity": "major", "requirement": "r", "evidence": "e",
                                 "affected_files": ["a.txt"], "required_correction": "c"}]
    if status in ("BLOCK", "BLOCKED"):
        document["blocked_reason"] = "needs a human"
    return document


def _adapter(cls, provider):
    return cls(RoleAssignment("reviewer", provider, provider.title(), provider, None))


def _request(tmp_path: Path, name: str, schema=CANONICAL, role="reviewer") -> AgentRequest:
    directory = tmp_path / name
    directory.mkdir(parents=True)
    prompt = directory / "prompt.md"
    prompt.write_text("review")
    return AgentRequest(role=role, prompt_file=prompt, working_directory=tmp_path, output_directory=directory,
                        report_schema=schema, session_id="s-1")


def _claude_answer(tmp_path, name, structured, **envelope):
    request = _request(tmp_path, name)
    body = {"type": "result", "subtype": "success", "is_error": False, "session_id": "claude-1",
            "structured_output": structured, **envelope}
    (request.output_directory / "provider.log").write_text(json.dumps(body) + "\n")
    return _adapter(ClaudeAdapter, "claude").parse_output(request, request.output_directory / "provider.log")


def _codex_answer(tmp_path, name, message):
    request = _request(tmp_path, name)
    (request.output_directory / "provider.log").write_text(json.dumps({"type": "thread.started", "thread_id": "codex-1"}) + "\n")
    (request.output_directory / "codex-last-message.txt").write_text(message)
    return _adapter(CodexAdapter, "codex").parse_output(request, request.output_directory / "provider.log")


# --- Provider-specific wire projections of one canonical schema ---

def test_claude_projection_drops_only_top_level_combinators_and_annotations():
    projected = input_schema(CANONICAL)
    assert not COMBINATORS & projected.keys() and not {"$schema", "$id", "title", "description"} & projected.keys()
    assert projected["properties"] == CANONICAL["properties"]  # nested constraints, e.g. evidence_reviewed's allOf, kept
    assert projected["required"] == CANONICAL["required"] and projected["additionalProperties"] is False
    assert input_schema(projected) == projected and "allOf" in CANONICAL  # idempotent; canonical untouched


@pytest.mark.parametrize("schema_name,documents", [
    ("review", [review(s) for s in ("PASS", "REVISE", "BLOCK", "BLOCKED")]),
    ("implementation-report", [REPORT]),
])
def test_claude_projection_only_relaxes_the_canonical_contract(schema_name, documents):
    canonical = load_schema(schema_name)
    projected = Draft202012Validator(input_schema(canonical))
    for document in documents:
        assert Draft202012Validator(canonical).is_valid(document) and projected.is_valid(document)


def test_codex_projection_is_strict_and_round_trips_to_canonical():
    projected = output_schema(CANONICAL)
    assert "allOf" not in projected and set(projected["required"]) == set(projected["properties"])
    for status in ("PASS", "REVISE", "BLOCK"):
        document = review(status)
        wire = {**document, "blocked_reason": document.get("blocked_reason")}  # strict wire: optional -> nullable
        assert Draft202012Validator(projected).is_valid(wire)
        assert omit_optional_nulls(wire, CANONICAL) == document


@pytest.mark.parametrize("schema", [{"type": "array", "items": {}}, {"$ref": "#/$defs/x", "type": "object"},
                                    {"oneOf": [{"type": "object"}]}])
def test_unsupported_schema_shapes_are_refused_not_guessed(schema):
    with pytest.raises(SchemaProjectionError):
        input_schema(schema)


def test_claude_reviewer_command_sends_projection_and_validates_canonical(tmp_path):
    adapter = _adapter(ClaudeAdapter, "claude")
    command = adapter.build_command(_request(tmp_path, "cmd"))
    sent = json.loads(command[command.index("--json-schema") + 1])
    assert sent == input_schema(CANONICAL) and "allOf" not in sent


# --- Same normalized result whichever provider reviewed ---

@pytest.mark.parametrize("status", ["PASS", "REVISE", "BLOCK", "BLOCKED"])
def test_both_providers_normalize_to_one_canonical_review(tmp_path, status):
    document = review(status)
    _, from_claude, claude_error = _claude_answer(tmp_path, "claude", document)
    wire = {**document, "blocked_reason": document.get("blocked_reason")}
    _, from_codex, codex_error = _codex_answer(tmp_path, "codex", json.dumps(wire))
    assert claude_error is None and codex_error is None and from_claude == from_codex == document
    normalized = []
    for provider, raw in (("claude", from_claude), ("codex", from_codex)):
        result, errors = normalize_review(raw, **IDENTITY, provider=provider, session_id=f"{provider}-session",
                                          reviewed_at="2026-10-05T05:01:00Z", browser_evidence=False)
        assert errors == [] and result["reviewer"] == {"provider": provider, "session_id": f"{provider}-session"}
        normalized.append({k: v for k, v in result.items() if k != "reviewer"})
    assert normalized[0] == normalized[1]
    assert normalized[0]["status"] == ("BLOCK" if status == "BLOCKED" else status)
    assert normalized[0]["reviewed_at"] == "2026-10-05T05:01:00Z"  # controller time, not the provider's claim


def test_malformed_or_incomplete_reviews_are_rejected(tmp_path):
    missing = review("PASS")
    del missing["findings"]
    assert "does not match schema" in _claude_answer(tmp_path, "missing", missing)[2]
    empty_revise = {**review("REVISE"), "findings": []}  # allowed by Claude's relaxed wire schema...
    assert Draft202012Validator(input_schema(CANONICAL)).is_valid(empty_revise)
    assert _claude_answer(tmp_path, "revise", empty_revise)[1] is None  # ...but refused by the canonical contract
    assert "not JSON" in _codex_answer(tmp_path, "prose", "looks good to me")[2]

    def normalized(raw, **overrides):
        return normalize_review(raw, **{**IDENTITY, **overrides}, provider="p", session_id="s",
                                reviewed_at="2026-10-05T05:00:00Z", browser_evidence=False)[1]
    assert normalized(None) == ["reviewer returned no structured review"]
    assert "identity" in normalized(review("PASS"), cycle=2)[0]
    narrow = {**review("PASS"), "evidence_reviewed": ["brief", "git_diff"]}
    assert "required authoritative evidence" in normalized(narrow)[0]
    duplicate = review("REVISE")
    duplicate["findings"] = duplicate["findings"] * 2
    assert "not unique" in normalized(duplicate)[0]
    assert "browser evidence" in normalize_review(review("PASS"), **IDENTITY, provider="p", session_id="s",
                                                  reviewed_at="2026-10-05T05:00:00Z", browser_evidence=True)[1][0]


# --- Failure classification from real CLI output ---

def _classify(tmp_path, adapter, name, *, stdout=None, stderr=None, exit_code=1, structured=None):
    request = _request(tmp_path, name, role="implementer")
    if stdout:
        (request.output_directory / "provider.log").write_bytes((SAMPLES / stdout).read_bytes())
    if stderr:
        (request.output_directory / "provider.stderr.log").write_bytes((SAMPLES / stderr).read_bytes())
    return adapter.classify_failure(request, exit_code=exit_code, timed_out=False, terminated=False, structured=structured)


def test_real_provider_errors_are_classified(tmp_path):
    codex, claude = _adapter(CodexAdapter, "codex"), _adapter(ClaudeAdapter, "claude")
    quota = _classify(tmp_path, codex, "q", stdout="codex-usage-limit.jsonl")
    assert quota.kind == QUOTA_EXHAUSTED and quota.rollover_eligible and "usage limit" in quota.detail
    assert _classify(tmp_path, codex, "t", stderr="codex-unknown-thread.stderr.txt").kind == SESSION_UNAVAILABLE
    assert _classify(tmp_path, claude, "s", stderr="claude-unknown-session.stderr.txt").kind == SESSION_UNAVAILABLE
    rejected = _classify(tmp_path, claude, "r", stdout="claude-schema-rejected.json")
    assert rejected.kind == SCHEMA_REJECTED and not rejected.rollover_eligible


def test_agent_text_is_never_mistaken_for_a_provider_failure(tmp_path):
    claude = _adapter(ClaudeAdapter, "claude")
    request = _request(tmp_path, "agent", role="implementer")
    envelope = {"type": "result", "subtype": "success", "is_error": False, "result": "I hit your usage limit check"}
    (request.output_directory / "provider.log").write_text(json.dumps(envelope))
    failure = claude.classify_failure(request, exit_code=0, timed_out=False, terminated=False, structured=None)
    assert failure.kind == INVALID_OUTPUT


def test_schema_rejection_fails_review_clearly_without_rollover(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setenv("FAKE_REVIEW_SEQUENCE", "SCHEMA")
    root, brief = make_project(tmp_path, rollover={"max_rollovers": 1, "approval": "automatic", "implementer": ["fake-b"]})
    state = Runner(preflight(brief, root)).run().state
    assert state["state"] == "FAILED" and state["failure"]["reason"] == "reviewer_failed"
    assert "[schema_rejected]" in state["failure"]["detail"] and state["rollover_history"] == []
