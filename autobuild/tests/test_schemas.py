"""Schemas compile, examples validate, and each encoded rule rejects what it should."""

import pytest
from jsonschema import Draft202012Validator

from autobuild.config import config_errors
from autobuild.implementations import brief_errors
from autobuild.run_state_checks import run_state_errors
from autobuild.schemas import SCHEMA_NAMES, load_schema, schema_errors
from helpers import example_brief, example_json, starter_config


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_valid(name):
    Draft202012Validator.check_schema(load_schema(name))


@pytest.mark.parametrize("name", ["EX-1-green.md", "EX-2-yellow.md", "EX-3-red.md"])
def test_example_briefs_validate(name):
    assert brief_errors(*example_brief(name)) == []


def test_example_documents_validate():
    assert run_state_errors(example_json("run-state.json")) == []
    assert schema_errors("review", example_json("review-01-revise.json")) == []
    assert schema_errors("review", example_json("review-02-pass.json")) == []
    assert schema_errors("validation", example_json("validation.json")) == []
    assert config_errors(starter_config()) == []


# --- Implementation brief rules ---

def test_green_rejects_human_requirements():
    meta, body = example_brief("EX-1-green.md")
    meta["human_requirements"] = ["Create an account"]
    assert any("human_requirements" in e for e in brief_errors(meta, body))


def test_green_rejects_human_validation():
    meta, body = example_brief("EX-1-green.md")
    meta["validation"]["human_validation_required"] = True
    assert brief_errors(meta, body)


def test_yellow_requires_a_human_gate_and_rationale():
    meta, body = example_brief("EX-2-yellow.md")
    meta["human_requirements"] = []
    del meta["autonomy_rationale"]
    errors = brief_errors(meta, body)
    assert any("human_requirements" in e for e in errors)
    assert any("autonomy_rationale" in e for e in errors)


def test_non_draft_requires_approval_but_draft_does_not():
    meta, body = example_brief("EX-1-green.md")
    del meta["approval"]
    assert any("approval" in e for e in brief_errors(meta, body))
    meta["status"] = "draft"
    assert brief_errors(meta, body) == []


def test_self_dependency_and_missing_section_rejected():
    meta, body = example_brief("EX-1-green.md")
    meta["depends_on"] = ["EX-1"]
    errors = brief_errors(meta, body.replace("## Non-Goals", "## Other"))
    assert any("depend on itself" in e for e in errors)
    assert any("Non-Goals" in e for e in errors)


def test_numeric_id_rejected():
    meta, body = example_brief("EX-1-green.md")
    meta["id"] = 4.2  # what unquoted `id: 4.2` parses to
    assert brief_errors(meta, body)


# --- Run state rules ---

def test_failed_requires_failure_record():
    state = example_json("run-state.json")
    state["state"] = "FAILED"
    assert any("failure" in e for e in run_state_errors(state))


def test_human_blocked_requires_gate():
    state = example_json("run-state.json")
    state["state"] = "HUMAN_BLOCKED"
    assert run_state_errors(state)


def test_stop_states_require_stop_flag():
    state = example_json("run-state.json")
    state["state"] = "STOPPED"
    assert run_state_errors(state)
    state["stop_requested"] = True
    assert run_state_errors(state) == []


def test_passed_requires_a_review():
    state = example_json("run-state.json")
    state["review_cycle"] = 0
    assert run_state_errors(state)
    state = example_json("run-state.json")
    state["agent_sessions"] = [s for s in state["agent_sessions"] if s["role"] != "reviewer"]
    assert run_state_errors(state)


def test_implementing_requires_branch_and_worktree():
    state = example_json("run-state.json")
    state["state"] = "IMPLEMENTING"
    state["worktree"] = None
    assert run_state_errors(state)


# --- Review rules ---

def test_pass_cannot_carry_major_finding():
    review = example_json("review-01-revise.json")
    review["status"] = "PASS"
    assert schema_errors("review", review)


def test_revise_requires_findings_and_blocked_requires_reason():
    review = example_json("review-01-revise.json")
    review["findings"] = []
    assert schema_errors("review", review)
    review["status"] = "BLOCKED"
    assert any("blocked_reason" in e for e in schema_errors("review", review))


def test_review_must_examine_brief_and_diff():
    review = example_json("review-02-pass.json")
    review["evidence_reviewed"] = ["implementer_summary", "validation_output"]
    assert schema_errors("review", review)


# --- Config rules ---

def test_config_rejects_prefix_that_covers_protected_branch():
    config = starter_config()
    config["git"]["protected_branches"] = ["main", "agent/release"]
    assert any("falls under branch_prefix" in e for e in config_errors(config))


def test_config_rejects_paths_outside_repository():
    for bad in ("/etc/passwd", "../other-repo", "docs/../../x"):
        config = starter_config()
        config["paths"]["roadmap"] = bad
        assert config_errors(config), bad


def test_config_remote_stop_needs_provider():
    config = starter_config()
    config["control"]["remote_stop_enabled"] = True
    assert config_errors(config)
