"""Bounded implementer rollover: triggers, budget, transitions, handoff integrity, fresh evidence, resume."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from autobuild import browser_runner, provider_registry
from autobuild.browser_contract import digest
from autobuild.cli import main
from autobuild.config import config_errors
from autobuild.preflight import PreflightError, preflight
from autobuild.provider_failures import (INVALID_OUTPUT, QUOTA_EXHAUSTED, SCHEMA_REJECTED, SESSION_UNAVAILABLE,
                                         TIMEOUT, TRANSIENT, ProviderFailure)
from autobuild.resume import resume_preflight
from autobuild.rollover_policy import decide
from autobuild.runner import Runner
from autobuild.run_state_checks import run_state_errors
from fake_provider import TEST_REGISTRY
from helpers import starter_config
from project_fixture import git, make_project

AUTO = {"max_rollovers": 1, "approval": "automatic", "implementer": ["fake-b"]}


def start(tmp_path, monkeypatch, *, modes=None, sequence="PASS", **options):
    for provider, mode in (modes or {}).items():
        monkeypatch.setenv("FAKE_AGENT_MODE_" + provider.upper().replace("-", "_"), mode)
    monkeypatch.setenv("FAKE_REVIEW_SEQUENCE", sequence)
    monkeypatch.setenv("FAKE_PROMPT_LOG", str(tmp_path / "prompts.log"))
    root, brief = make_project(tmp_path, **options)
    main_before = git(root, "rev-parse", "main").strip()
    outcome = Runner(preflight(brief, root)).run()
    assert git(root, "rev-parse", "main").strip() == main_before
    assert run_state_errors(outcome.state) == []
    return root, outcome


def attempts(state):
    return [(a["provider"], a["mode"]) for a in state["revision_history"]]


# --- Successful rollover ---

def test_quota_failure_rolls_over_through_verified_handoff(tmp_path, monkeypatch, fake_registry):
    root, outcome = start(tmp_path, monkeypatch, modes={"fake-a": "quota"}, rollover=AUTO)
    state, run = outcome.state, outcome.run_dir
    assert state["state"] == "COMPLETED", state.get("failure") or state.get("human_gate")
    assert attempts(state) == [("fake-a", "initial"), ("fake-b", "rollover")]
    first, second = state["revision_history"]
    assert first["failure"]["kind"] == QUOTA_EXHAUSTED and second["failure"] is None
    assert second["resume_session_id"] is None and second["session_id"] != first["session_id"]

    [record] = state["rollover_history"]
    assert (record["status"], record["from_provider"], record["to_provider"], record["approval"],
            record["failed_attempt"], record["replacement_attempt"]) == ("executed", "fake-a", "fake-b", "automatic", 1, 2)
    handoff_path = run / record["handoff_artifact"]
    assert digest(handoff_path) == record["handoff_sha256"]
    handoff = json.loads(handoff_path.read_text())
    assert handoff["failure"]["kind"] == QUOTA_EXHAUSTED and handoff["rollover_count"] == 0
    assert (handoff["from"]["provider"], handoff["to"]["provider"]) == ("fake-a", "fake-b")
    assert handoff["snapshot_tree"] == record["snapshot_tree"] and handoff["changed_paths"] == ["partial.txt"]
    assert handoff["protected_refs"] == state["protected_refs"] and handoff["brief"]["sha256"] == state["brief_sha256"]
    assert digest(run / handoff["source"]["diff.patch"]["path"]) == handoff["source"]["diff.patch"]["sha256"]

    # Old evidence never existed for the failed attempt; fresh validation and review cover the takeover.
    assert [v["attempt"] for v in state["validation_history"]] == [2]
    assert state["review_history"][0]["validation_artifact"] == "validation/cycle-02/results.json"
    prompt = (run / "implementation/cycle-02/prompt.md").read_text()
    assert "Take Over An Existing Implementation" in prompt and "NEW implementer session" in prompt
    assert "Continue the existing implementer session" not in prompt and "continue your" not in prompt.lower()
    assert str(handoff_path) in prompt and "partial.txt" in prompt and "## Approved Brief" in prompt

    files = git(root, "show", "--name-only", "--format=", state["branch"]).split()
    assert sorted(files) == ["feature.txt", "partial.txt"]  # existing work preserved, remaining work added
    message = git(root, "log", "-1", "--format=%B", state["branch"])
    assert "Autobuild-Implementer: fake-b" in message and "Autobuild-Rollover: fake-a -> fake-b (quota_exhausted)" in message
    assert "took over from fake-a" in outcome.report and "#1 fake-a -> fake-b" in outcome.report


def test_rollover_during_revision_reruns_validation_browser_and_fresh_review(tmp_path, monkeypatch, fake_registry):
    def command(worktree, inputs, writable, environment):  # benign unit worker, as in test_browser
        worker = Path(browser_runner.__file__).with_name("browser_worker.py")
        return ["/usr/bin/env", *[f"{k}={v}" for k, v in environment.items()], sys.executable, str(worker),
                str(inputs / "request.json")]
    monkeypatch.setattr(browser_runner, "sandbox_command", command)
    monkeypatch.setenv("FAKE_BROWSER_REVIEW", "1")
    script = "from pathlib import Path; raise SystemExit(0 if Path('feature.txt').read_text().endswith('1') else 1)"
    gate = {"id": "smoke", "kind": "e2e", "command": [sys.executable, "-c", script]}
    _, outcome = start(tmp_path, monkeypatch, modes={"fake-a": "quota_on_resume"}, sequence="REVISE,PASS",
                       rollover=AUTO, browser_gates=[gate])
    state, run = outcome.state, outcome.run_dir
    assert state["state"] == "COMPLETED", state.get("failure") or state.get("human_gate")
    assert attempts(state) == [("fake-a", "initial"), ("fake-a", "resume"), ("fake-b", "rollover")]
    assert [(v["attempt"], v["review_cycle"]) for v in state["validation_history"]] == [(1, 1), (3, 2)]
    assert [(b["attempt"], b["passed"]) for b in state["browser_history"]] == [(1, False), (3, True)]
    final = state["review_history"][-1]
    assert final["status"] == "PASS" and final["validation_artifact"] == "validation/cycle-03/results.json"
    assert final["browser_artifact"] == "browser/cycle-03/results.json"
    assert final["snapshot_tree"] != state["review_history"][0]["snapshot_tree"]
    reviewers = [s["session_id"] for s in state["agent_sessions"] if s["role"] == "reviewer"]
    assert len(set(reviewers)) == 2
    takeover = (run / "implementation/cycle-03/prompt.md").read_text()
    assert "Required Review Findings (still open)" in takeover and "R1-1" in takeover
    assert "Rollover (controller record)" in (run / "review/review-02-prompt.md").read_text()
    assert state["checkpoint"]["committed"]


def test_session_scoped_failure_may_restart_same_provider(tmp_path, monkeypatch, fake_registry):
    rollover = {"max_rollovers": 1, "approval": "automatic", "implementer": ["fake-a"]}
    _, outcome = start(tmp_path, monkeypatch, modes={"fake-a": "session_gone_on_resume"}, sequence="REVISE,PASS",
                       rollover=rollover)
    state = outcome.state
    assert state["state"] == "COMPLETED", state.get("human_gate")
    assert attempts(state) == [("fake-a", "initial"), ("fake-a", "resume"), ("fake-a", "rollover")]
    assert state["revision_history"][1]["failure"]["kind"] == SESSION_UNAVAILABLE
    assert state["revision_history"][2]["session_id"] != state["revision_history"][0]["session_id"]


# --- What never triggers rollover ---

def test_transient_failure_does_not_roll_over(tmp_path, monkeypatch, fake_registry):
    _, outcome = start(tmp_path, monkeypatch, modes={"fake-a": "transient"}, rollover=AUTO)
    state = outcome.state
    assert state["state"] == "FAILED" and state["failure"]["reason"] == "provider_failed"
    assert state["failure"]["recoverable"] and "[transient]" in state["failure"]["detail"]
    assert state["rollover_history"] == [] and state["revision_history"][0]["failure"]["kind"] == TRANSIENT


@pytest.mark.parametrize("commands", [None, [{"name": "marker", "kind": "test",
                                              "command": ["grep", "-q", "1", "feature.txt"]}]])
def test_test_failure_and_revise_use_same_session_not_rollover(tmp_path, monkeypatch, fake_registry, commands):
    _, outcome = start(tmp_path, monkeypatch, sequence="REVISE,PASS", rollover=AUTO, commands=commands)
    state = outcome.state
    assert state["state"] == "COMPLETED"
    assert state["rollover_history"] == []
    assert attempts(state) == [("fake-a", "initial"), ("fake-a", "resume")]
    assert state["revision_history"][1]["resume_session_id"] == state["revision_history"][0]["session_id"]


# --- Fail closed ---

@pytest.mark.parametrize("rollover,modes,reason", [
    (AUTO, {"fake-a": "quota", "fake-b": "quota"}, "budget exhausted"),
    ({**AUTO, "implementer": ["fake-a"]}, {"fake-a": "quota"}, "unsupported provider transition"),
    ({**AUTO, "implementer": ["fake-missing"]}, {"fake-a": "quota"}, "no configured replacement implementer is available"),
    (None, {"fake-a": "quota"}, "rollover is not configured"),
    ({**AUTO, "on": ["session_unavailable"]}, {"fake-a": "quota"}, "not configured for quota_exhausted"),
])
def test_blocked_rollover_preserves_work_without_checkpoint(tmp_path, monkeypatch, fake_registry, rollover, modes, reason):
    root, outcome = start(tmp_path, monkeypatch, modes=modes, rollover=rollover)
    state = outcome.state
    assert state["state"] == "HUMAN_BLOCKED" and reason in state["human_gate"]["reason"]
    assert state["last_commit"] is None and not state["checkpoint"]["committed"]
    assert git(root, "rev-parse", state["branch"]).strip() == state["base_commit"]
    assert Path(state["worktree"], "partial.txt").exists()
    blocked = state["rollover_history"][-1]
    assert blocked["status"] == "blocked" and reason in blocked["reason"]
    assert digest(outcome.run_dir / blocked["handoff_artifact"]) == blocked["handoff_sha256"]
    assert sum(r["status"] == "executed" for r in state["rollover_history"]) <= 1


def test_unavailable_replacement_is_a_preflight_warning(tmp_path, fake_registry):
    root, brief = make_project(tmp_path, rollover={**AUTO, "implementer": ["fake-missing"]})
    assert any("rollover implementer fake-missing is unavailable" in w for w in preflight(brief, root).warnings)


# --- Human approval, resume and integrity ---

def test_human_approval_prepares_then_resume_executes(tmp_path, monkeypatch, fake_registry, capsys):
    root, first = start(tmp_path, monkeypatch, modes={"fake-a": "quota"}, rollover={**AUTO, "approval": "human"})
    assert first.state["state"] == "HUMAN_BLOCKED" and "prepared for approval" in first.state["human_gate"]["reason"]
    assert first.state["rollover_history"][0]["status"] == "prepared"
    plan = resume_preflight(first.run_dir, root)
    assert plan.resume_rollover["action"] == "execute"
    assert main(["resume", str(first.run_dir), "--project", str(root), "--dry-run"]) == 0
    assert "Resume mode: rollover 1 from fake-a (quota_exhausted) to fake-b" in capsys.readouterr().out
    second = Runner(resume_preflight(first.run_dir, root)).run()
    state = second.state
    assert state["state"] == "COMPLETED"
    assert attempts(state) == [("fake-a", "initial"), ("fake-b", "rollover")]
    assert state["rollover_history"][0]["status"] == "executed" and state["rollover_history"][0]["approval"] == "human"
    assert main(["evidence", str(second.run_dir)]) == 0
    out = capsys.readouterr().out
    assert "implementer fake-b; reviewer fake-a; rollovers executed 1" in out and "rollover 1: fake-a -> fake-b" in out


def _tamper_handoff(run, root, state):
    path = run / state["rollover_history"][0]["handoff_artifact"]
    path.write_text(path.read_text().replace('"fake-b"', '"fake-c"'))


def _tamper_diff(run, root, state):
    (run / "rollover/rollover-01/diff.patch").write_text("forged\n")


def _change_worktree(run, root, state):
    Path(state["worktree"], "partial.txt").write_text("edited after the handoff\n")


def _move_protected_ref(run, root, state):
    git(root, "commit", "--allow-empty", "-q", "-m", "human work on main")


@pytest.mark.parametrize("tamper,message", [
    (_tamper_handoff, "handoff 1 is missing or modified"),
    (_tamper_diff, "handoff-referenced artifact missing or modified: rollover/rollover-01/diff.patch"),
    (_change_worktree, "worktree source changed since the handoff"),
    (_move_protected_ref, "protected refs changed since the handoff"),
])
def test_prepared_rollover_refuses_takeover_after_tampering(tmp_path, monkeypatch, fake_registry, tamper, message):
    root, first = start(tmp_path, monkeypatch, modes={"fake-a": "quota"}, rollover={**AUTO, "approval": "human"})
    tamper(first.run_dir, root, first.state)
    with pytest.raises(PreflightError) as error:
        resume_preflight(first.run_dir, root)
    assert any(message in issue for issue in error.value.issues), error.value.issues


def test_runner_rejects_handoff_changed_before_takeover(tmp_path, monkeypatch, fake_registry):
    from autobuild import runner as runner_module
    real = runner_module.build_handoff

    def build_then_tamper(**kwargs):
        artifact, sha, evidence = real(**kwargs)
        Path(kwargs["state"]["worktree"], "partial.txt").write_text("changed between handoff and takeover\n")
        return artifact, sha, evidence
    monkeypatch.setattr(runner_module, "build_handoff", build_then_tamper)
    _, outcome = start(tmp_path, monkeypatch, modes={"fake-a": "quota"}, rollover=AUTO)
    state = outcome.state
    assert state["state"] == "FAILED" and state["failure"]["reason"] == "rollover_handoff_invalid"
    assert not state["failure"]["recoverable"] and state["last_commit"] is None
    assert [a["provider"] for a in state["revision_history"]] == ["fake-a"]


def test_blocked_rollover_is_redecided_on_resume_when_replacement_returns(tmp_path, monkeypatch, fake_registry):
    broken = {"version": 1, "providers": {**TEST_REGISTRY["providers"],
              "fake-b": {**TEST_REGISTRY["providers"]["fake-b"], "executable": "definitely-not-installed-autobuild"}}}
    monkeypatch.setattr(provider_registry, "load_registry", lambda: broken)
    root, first = start(tmp_path, monkeypatch, modes={"fake-a": "quota"}, rollover=AUTO)
    assert first.state["rollover_history"][0]["status"] == "blocked"
    monkeypatch.setattr(provider_registry, "load_registry", lambda: TEST_REGISTRY)
    plan = resume_preflight(first.run_dir, root)
    assert plan.resume_rollover["action"] == "redecide"
    state = Runner(plan).run().state
    assert state["state"] == "COMPLETED"
    assert [(r["status"], r["approval"]) for r in state["rollover_history"]] == [("blocked", "automatic"), ("executed", "human")]


def test_resume_without_allowed_rollover_continues_same_session(tmp_path, monkeypatch, fake_registry):
    root, first = start(tmp_path, monkeypatch, modes={"fake-a": "quota"})  # rollover not configured
    assert first.state["state"] == "HUMAN_BLOCKED"
    monkeypatch.setenv("FAKE_AGENT_MODE_FAKE_A", "write")  # e.g. the quota reset
    plan = resume_preflight(first.run_dir, root)
    assert plan.resume_rollover is None and plan.assignment.provider == "fake-a"
    state = Runner(plan).run().state
    assert state["state"] == "COMPLETED" and attempts(state) == [("fake-a", "initial"), ("fake-a", "resume")]


def test_resume_after_executed_rollover_continues_replacement_session(tmp_path, monkeypatch, fake_registry):
    root, first = start(tmp_path, monkeypatch, modes={"fake-a": "quota"}, sequence="BLOCK,PASS", rollover=AUTO)
    assert first.state["state"] == "HUMAN_BLOCKED" and first.state["rollover_history"][0]["status"] == "executed"
    plan = resume_preflight(first.run_dir, root)
    assert plan.resume_rollover is None and plan.assignment.provider == "fake-b"
    state = Runner(plan).run().state
    assert state["state"] == "COMPLETED"
    assert attempts(state) == [("fake-a", "initial"), ("fake-b", "rollover"), ("fake-b", "resume")]
    assert state["revision_history"][2]["resume_session_id"] == state["revision_history"][1]["session_id"]


# --- Policy and configuration ---

def _health(available):
    return lambda provider: (provider in available, "ok" if provider in available else "missing")


@pytest.mark.parametrize("kind", [TRANSIENT, TIMEOUT, SCHEMA_REJECTED, INVALID_OUTPUT, "unknown", "interrupted"])
def test_non_provider_failures_never_trigger(kind):
    config = {"rollover": {"max_rollovers": 1, "approval": "automatic", "implementer": ["b"]}}
    assert not decide(config, ProviderFailure(kind, "x"), "a", 0, _health({"b"})).allowed


def test_decision_order_health_budget_and_scope():
    config = {"rollover": {"max_rollovers": 1, "approval": "automatic", "implementer": ["a", "b", "c"]}}
    quota = ProviderFailure(QUOTA_EXHAUSTED, "x")
    assert decide(config, quota, "a", 0, _health({"a", "b", "c"})).replacement == "b"  # a cannot replace itself
    assert decide(config, quota, "a", 0, _health({"a", "c"})).replacement == "c"  # b unavailable
    assert decide(config, ProviderFailure(SESSION_UNAVAILABLE, "x"), "a", 0, _health({"a"})).replacement == "a"
    assert "budget exhausted" in decide(config, quota, "a", 1, _health({"b"})).reason


@pytest.mark.parametrize("rollover,fragment", [
    ({"max_rollovers": 2, "approval": "automatic", "implementer": ["claude"]}, "maximum"),
    ({"max_rollovers": 1, "approval": "automatic", "implementer": ["nope"]}, "unknown provider"),
    ({"max_rollovers": 1, "approval": "automatic", "implementer": ["claude"], "on": ["transient"]}, "transient"),
    ({"max_rollovers": 1, "approval": "sometimes", "implementer": ["claude"]}, "sometimes"),
])
def test_rollover_config_is_bounded(rollover, fragment):
    assert any(fragment in error for error in config_errors({**starter_config(), "rollover": rollover}))
