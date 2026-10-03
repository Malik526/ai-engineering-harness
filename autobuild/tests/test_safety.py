"""Protected branches, default-deny operations, and config-aware run-state checks."""

from pathlib import Path

from autobuild.config import ProjectConfig
from autobuild.policy_loader import load_policy
from autobuild.run_state_checks import run_state_errors
from autobuild.safety import is_operation_allowed, is_protected_branch
from helpers import example_json, starter_config


def _config(**limits) -> ProjectConfig:
    data = starter_config()
    data["limits"].update(limits)
    return ProjectConfig(root=Path("/tmp/project"), data=data)


def test_protected_branch_matches_ref_forms():
    for ref in ("main", "refs/heads/main", "origin/main", "refs/remotes/origin/main"):
        assert is_protected_branch(ref, ["main"])
    assert not is_protected_branch("agent/main-fix", ["main"])


def test_operations_default_deny():
    assert is_operation_allowed("run_tests")
    assert not is_operation_allowed("force_push")
    assert not is_operation_allowed("some_new_operation")


def test_allowed_and_prohibited_are_disjoint():
    policy = load_policy("safety")
    assert not set(policy["allowed"]) & set(policy["prohibited"])


def test_example_run_state_passes_config_checks():
    assert run_state_errors(example_json("run-state.json"), _config()) == []


def test_run_on_protected_branch_rejected():
    state = example_json("run-state.json")
    state["branch"] = "main"
    assert any("protected" in e for e in run_state_errors(state, _config()))


def test_run_branch_must_use_prefix():
    state = example_json("run-state.json")
    state["branch"] = "feature/x"
    assert any("does not start with" in e for e in run_state_errors(state, _config()))


def test_review_cycle_limit_enforced():
    state = example_json("run-state.json")
    assert any("exceeds limit" in e for e in run_state_errors(state, _config(max_review_cycles=1)))


def test_reviewer_must_be_fresh_session_even_with_same_provider():
    state = example_json("run-state.json")
    for session in state["agent_sessions"]:
        session["provider"] = "claude"  # same provider in both roles is allowed...
    assert run_state_errors(state) == []
    state["agent_sessions"][1]["session_id"] = "impl-7f3a"  # ...reusing the implementer session is not
    assert any("reuses implementer session" in e for e in run_state_errors(state))


def test_updated_before_started_rejected():
    state = example_json("run-state.json")
    state["updated_at"] = "2026-10-03T13:00:00Z"
    assert run_state_errors(state)
