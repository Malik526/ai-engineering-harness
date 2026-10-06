"""0.7 governance: budgets, canonical stop reasons, remote stop, notifications, governed resume."""

import json
import os
import socketserver
import threading
import time
from pathlib import Path

import pytest
import yaml

from autobuild import governance
from autobuild.config import config_errors
from autobuild.email_notifier import EmailNotifier
from autobuild.file_control import FileStopController
from autobuild.notification_payload import event_for
from autobuild.preflight import PreflightError, preflight
from autobuild.resume import resume_preflight
from autobuild.run_state_checks import run_state_errors
from autobuild.runner import Runner
from autobuild import stop_reasons
from helpers import starter_config
from project_fixture import git, make_project

ROLL = {"max_rollovers": 1, "approval": "automatic", "implementer": ["fake-b"]}


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(governance, "POLL_SECONDS", 0.05)


def project(tmp_path, monkeypatch, *, limits=None, notify=False, remote_stop=False, modes=None, sequence="PASS",
            **options):
    for provider, mode in (modes or {}).items():
        monkeypatch.setenv("FAKE_AGENT_MODE_" + provider.upper().replace("-", "_"), mode)
    monkeypatch.setenv("FAKE_REVIEW_SEQUENCE", sequence)
    monkeypatch.setenv("FAKE_PID_FILE", str(tmp_path / "agent.pid"))
    root, brief = make_project(tmp_path, **options)
    path = root / ".autobuild/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["limits"].update(limits or {})
    if notify:
        config["notifications"] = {"enabled": True, "provider": "file"}
    if remote_stop:
        config["control"] = {"remote_stop_enabled": True, "provider": "file"}
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    git(root, "commit", "-q", "--allow-empty", "-am", "governance config")
    return root, brief


def run(root, brief):
    main = git(root, "rev-parse", "main").strip()
    outcome = Runner(preflight(brief, root)).run()
    assert git(root, "rev-parse", "main").strip() == main
    assert run_state_errors(outcome.state) == []
    return outcome


def stopped_with(outcome, code):
    reason = outcome.state["stop_reason"]
    assert reason is not None and reason["code"] == code, (outcome.state["state"], reason, outcome.state.get("failure"))
    return reason


def preserved(outcome, root):
    state = outcome.state
    assert state["last_commit"] is None and git(root, "rev-parse", state["branch"]).strip() == state["base_commit"]
    assert Path(state["worktree"]).is_dir() and (outcome.run_dir / "state.json").is_file()


def notifications(outcome):
    return [json.loads(p.read_text()) for p in sorted((outcome.run_dir / "notifications").glob("*.json"))]


def pid_alive(tmp_path):
    pid = int((tmp_path / "agent.pid").read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return Path(f"/proc/{pid}/status").read_text().find("State:\tZ") == -1


# --- 1. Runtime budget ---

def test_runtime_budget_stops_at_the_next_boundary(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setattr(governance, "MINUTE", 0.001)  # 1 configured minute = 1 ms
    root, brief = project(tmp_path, monkeypatch, limits={"max_runtime_minutes": 1})
    outcome = run(root, brief)
    reason = stopped_with(outcome, stop_reasons.RUNTIME_BUDGET)
    assert outcome.state["state"] == "HUMAN_BLOCKED" and reason["limit"]["name"] == "limits.max_runtime_minutes"
    assert "--override-limits" in outcome.state["human_gate"]["human_action"][0]
    preserved(outcome, root)


def test_runtime_budget_terminates_a_running_provider(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setattr(governance, "MINUTE", 0.5)  # 1 configured minute = 0.5 s
    root, brief = project(tmp_path, monkeypatch, limits={"max_runtime_minutes": 1}, modes={"fake-a": "partial_sleep"})
    started = time.monotonic()
    outcome = run(root, brief)
    assert time.monotonic() - started < 30
    stopped_with(outcome, stop_reasons.RUNTIME_BUDGET)
    assert not pid_alive(tmp_path)
    assert outcome.state["revision_history"][0]["failure"]["kind"] == "interrupted"
    assert Path(outcome.state["worktree"], "partial.txt").exists()
    preserved(outcome, root)


# --- 2-4. Review, revision, validation, rollover and usage budgets ---

def test_review_cycle_budget_has_canonical_reason(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, sequence="REVISE", max_cycles=2)
    reason = stopped_with(run(root, brief), stop_reasons.REVIEW_BUDGET)
    assert reason["limit"] == {"name": "limits.max_review_cycles", "limit": 2, "used": 2}


def test_revision_attempt_budget(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, limits={"max_revision_attempts": 1}, sequence="REVISE,REVISE,PASS")
    outcome = run(root, brief)
    reason = stopped_with(outcome, stop_reasons.REVISION_BUDGET)
    assert reason["limit"]["used"] == 1 and len(outcome.state["revision_history"]) == 2
    preserved(outcome, root)


def test_validation_attempt_budget(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, limits={"max_validation_attempts": 1}, sequence="REVISE,PASS")
    outcome = run(root, brief)
    stopped_with(outcome, stop_reasons.VALIDATION_BUDGET)
    assert len(outcome.state["validation_history"]) == 1 and len(outcome.state["revision_history"]) == 2


def test_usage_budget_uses_provider_reported_tokens(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setenv("FAKE_USAGE_TOKENS", "6000")
    root, brief = project(tmp_path, monkeypatch, limits={"max_usage_tokens": 10000}, sequence="REVISE,PASS")
    outcome = run(root, brief)
    reason = stopped_with(outcome, stop_reasons.USAGE_BUDGET)
    assert reason["limit"]["used"] == 12000  # implementation + review; the next operation was refused
    usage = [op["usage"]["total_tokens"] for op in outcome.state["governance"]["operations"] if op["usage"]]
    assert usage == [6000, 6000]


def test_rollover_budget_is_distinct_from_provider_failure(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, modes={"fake-a": "quota", "fake-b": "quota"}, rollover=ROLL)
    budget = run(root, brief)
    reason = stopped_with(budget, stop_reasons.ROLLOVER_BUDGET)
    assert reason["limit"] == {"name": "rollover.max_rollovers", "limit": 1, "used": 1}

    other, other_brief = project(tmp_path / "other", monkeypatch, modes={"fake-a": "quota"},
                                 rollover={**ROLL, "implementer": ["fake-missing"]})
    stopped_with(run(other, other_brief), stop_reasons.PROVIDER_FAILURE)


def test_rollover_consumes_but_never_resets_other_budgets(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, limits={"max_revision_attempts": 1}, modes={"fake-a": "quota"},
                          sequence="REVISE,PASS", rollover=ROLL)
    outcome = run(root, brief)
    state = outcome.state
    assert [a["mode"] for a in state["revision_history"]] == ["initial", "rollover"]
    assert state["rollover_history"][0]["status"] == "executed"
    stopped_with(outcome, stop_reasons.REVISION_BUDGET)  # the takeover was revision 1 of 1
    kinds = [op["kind"] for op in state["governance"]["operations"]]
    assert kinds == ["implementation", "implementation", "validation", "review"]


def test_unknown_provider_failure_fails_closed(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, modes={"fake-a": "fail"}, rollover=ROLL)
    outcome = run(root, brief)
    assert outcome.state["state"] == "FAILED" and outcome.state["rollover_history"] == []
    stopped_with(outcome, stop_reasons.PROVIDER_FAILURE)
    assert outcome.state["revision_history"][0]["failure"]["kind"] == "unknown"


# --- 5-7. Remote stop ---

def test_remote_stop_before_provider_start(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, remote_stop=True)
    plan = preflight(brief, root)
    FileStopController(plan.run_dir).request_stop(plan.run_id, "test", "operator stop")
    outcome = Runner(plan).run()
    assert outcome.state["state"] == "STOPPED" and outcome.state["stop_requested"]
    assert "operator stop" in stopped_with(outcome, stop_reasons.REMOTE_STOP)["detail"]
    assert outcome.state["agent_sessions"] == [] and outcome.state["revision_history"] == []
    assert FileStopController(plan.run_dir).check_stop_requested(plan.run_id) is None  # acknowledged


def test_remote_stop_terminates_running_provider_and_preserves_work(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, remote_stop=True, modes={"fake-a": "partial_sleep"}, notify=True)
    plan = preflight(brief, root)
    timer = threading.Timer(1.0, lambda: FileStopController(plan.run_dir).request_stop(plan.run_id, "test"))
    timer.start()
    started = time.monotonic()
    outcome = Runner(plan).run()
    timer.join()
    assert time.monotonic() - started < 30 and not pid_alive(tmp_path)
    assert outcome.state["state"] == "STOPPED"
    stopped_with(outcome, stop_reasons.REMOTE_STOP)
    assert outcome.state["revision_history"][0]["failure"]["kind"] == "interrupted"
    assert Path(outcome.state["worktree"], "partial.txt").read_text() == "partial work before the stop\n"
    assert (outcome.run_dir / "implementation/cycle-01/prompt.md").is_file()
    [stopped] = notifications(outcome)
    assert stopped["event"] == "stopped" and "autobuild resume" in stopped["human_action"][0]
    assert "partial.txt" in outcome.report  # the report shows the preserved work from a controller snapshot
    preserved(outcome, root)


def test_resume_after_remote_stop_keeps_history(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, remote_stop=True, modes={"fake-a": "partial_sleep"})
    plan = preflight(brief, root)
    threading.Timer(0.5, lambda: FileStopController(plan.run_dir).request_stop(plan.run_id, "test")).start()
    first = Runner(plan).run()
    assert first.state["state"] == "STOPPED"
    monkeypatch.setenv("FAKE_AGENT_MODE_FAKE_A", "write")
    second = Runner(resume_preflight(first.run_dir, root)).run()
    state = second.state
    assert state["state"] == "COMPLETED" and state["stop_reason"]["code"] == stop_reasons.COMPLETED
    assert [a["mode"] for a in state["revision_history"]] == ["initial", "resume"]
    assert len(state["governance"]["segments"]) == 2
    assert state["governance"]["operations"][0]["kind"] == "implementation"  # the stopped attempt is still accounted


def test_pending_stop_request_blocks_resume_until_cleared(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, remote_stop=True, sequence="BLOCK,PASS")
    first = run(root, brief)
    controller = FileStopController(first.run_dir)
    controller.request_stop(first.state["run_id"], "test")
    with pytest.raises(PreflightError, match="stop request is pending"):
        resume_preflight(first.run_dir, root)
    assert controller.clear()
    assert Runner(resume_preflight(first.run_dir, root)).run().state["state"] == "COMPLETED"


# --- 8-9. Notifications ---

@pytest.mark.parametrize("modes,sequence,event,status", [
    ({}, "PASS", "completed", "COMPLETED"),
    ({}, "BLOCK", "human_action_required", "HUMAN_BLOCKED"),
    ({"fake-a": "fail"}, "PASS", "failed", "FAILED"),
    ({}, "REVISE", "budget_exhausted", "HUMAN_BLOCKED"),
])
def test_final_notification_is_structured(tmp_path, monkeypatch, fake_registry, modes, sequence, event, status):
    root, brief = project(tmp_path, monkeypatch, notify=True, modes=modes, sequence=sequence, max_cycles=1)
    outcome = run(root, brief)
    [payload] = notifications(outcome)
    assert (payload["event"], payload["status"]) == (event, status)
    assert payload["stop_reason"]["code"] == outcome.state["stop_reason"]["code"]
    assert payload["providers"]["implementer"] == "fake-a" and payload["branch"] == outcome.state["branch"]
    assert payload["counts"]["implementation_attempts"] == len(outcome.state["revision_history"])
    text = (outcome.run_dir / "notifications").glob("*.txt").__next__().read_text()
    assert f"T-1 " in text.splitlines()[0] and "Stop reason:" in text


def test_rollover_notification_precedes_final(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, notify=True, modes={"fake-a": "quota"}, rollover=ROLL)
    events = notifications(run(root, brief))
    assert [e["event"] for e in events] == ["rollover", "completed"]
    assert "fake-b takes over" in events[0]["summary"] and events[1]["counts"]["rollovers"] == 1
    assert events[0]["providers"]["implementer"] == "fake-b"  # the incoming replacement, not the failed provider


def test_notification_failure_never_affects_the_run(tmp_path, monkeypatch, fake_registry):
    from autobuild import file_notifier

    def broken(self, payload):
        raise ConnectionError("mail server down")
    monkeypatch.setattr(file_notifier.FileNotifier, "send", broken)
    root, brief = project(tmp_path, monkeypatch, notify=True)
    outcome = run(root, brief)
    assert outcome.state["state"] == "COMPLETED" and outcome.state["last_commit"]
    assert "mail server down" in (outcome.run_dir / "notifications/delivery-failures.log").read_text()


def test_email_notifier_delivers_over_smtp(tmp_path, monkeypatch, fake_registry):
    received = []

    class SMTPHandler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 test\r\n")
            data = False
            for raw in self.rfile:
                line = raw.decode().rstrip("\r\n")
                if data:
                    if line == ".":
                        data = False
                        self.wfile.write(b"250 queued\r\n")
                    else:
                        received.append(line)
                    continue
                command = line.split(" ")[0].upper()
                if command == "DATA":
                    data = True
                    self.wfile.write(b"354 go\r\n")
                elif command == "QUIT":
                    self.wfile.write(b"221 bye\r\n")
                    return
                else:
                    self.wfile.write(b"250 ok\r\n")

    server = socketserver.TCPServer(("127.0.0.1", 0), SMTPHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        settings = {"to": ["ops@example.invalid"], "from": "autobuild@example.invalid", "smtp_host": "127.0.0.1",
                    "smtp_port": server.server_address[1], "security": "none"}
        root, brief = project(tmp_path, monkeypatch, notify=True)
        outcome = run(root, brief)
        [payload] = notifications(outcome)
        EmailNotifier(settings, timeout=5).send(payload)
    finally:
        server.shutdown()
        server.server_close()
    from email import policy
    from email.parser import Parser
    message = Parser(policy=policy.default).parsestr("\n".join(received))
    assert message["Subject"] == "Fixture Autobuild — T-1 COMPLETED" and message["To"] == "ops@example.invalid"
    assert "Stop reason: completed" in message.get_content()


# --- 10-12. Governed resume ---

def test_budget_stop_resumes_only_with_explicit_override(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, limits={"max_revision_attempts": 1}, sequence="REVISE,REVISE,PASS")
    first = run(root, brief)
    stopped_with(first, stop_reasons.REVISION_BUDGET)
    with pytest.raises(PreflightError, match="budget exhausted"):
        resume_preflight(first.run_dir, root)
    path = root / ".autobuild/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["limits"]["max_revision_attempts"] = 2
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    with pytest.raises(PreflightError, match="--override-limits"):
        resume_preflight(first.run_dir, root)
    second = Runner(resume_preflight(first.run_dir, root, override_limits=True)).run()
    state = second.state
    assert state["state"] == "COMPLETED"
    assert state["governance"]["overrides"][0]["changes"] == [{"key": "limits.max_revision_attempts", "from": 1, "to": 2}]
    # Counters continued from the first session instead of resetting.
    assert len(state["revision_history"]) == 3 and state["review_cycle"] == 3
    assert len(state["governance"]["segments"]) == 2
    assert [op["kind"] for op in state["governance"]["operations"]].count("review") == 3
    assert "Limit overrides: limits.max_revision_attempts 1 -> 2" in second.report


def test_lowered_limit_is_also_an_explicit_override(tmp_path, monkeypatch, fake_registry):
    root, brief = project(tmp_path, monkeypatch, sequence="BLOCK,PASS")
    first = run(root, brief)
    path = root / ".autobuild/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["limits"]["max_validation_attempts"] = 1  # already used: a resume would immediately exceed it
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    with pytest.raises(PreflightError, match="--override-limits"):
        resume_preflight(first.run_dir, root)
    outcome = Runner(resume_preflight(first.run_dir, root, override_limits=True)).run()
    stopped_with(outcome, stop_reasons.VALIDATION_BUDGET)


# --- Configuration and reasons ---

@pytest.mark.parametrize("change,fragment", [
    ({"limits": {"max_revision_attempts": 0},
      "rollover": {"max_rollovers": 1, "approval": "automatic", "implementer": ["claude"]}}, "could never run"),
    ({"control": {"remote_stop_enabled": True, "provider": "github"}}, "not implemented"),
    ({"limits": {"max_runtime_minutes": 0}}, "minimum"),
    ({"notifications": {"enabled": True, "provider": "email"}}, "email"),
])
def test_impossible_governance_config_is_rejected(change, fragment):
    config = starter_config()
    for section, values in change.items():
        config[section] = {**config.get(section, {}), **values} if section == "limits" else values
    assert any(fragment in error for error in config_errors(config)), config_errors(config)


def test_usage_budget_requires_providers_that_report_usage(tmp_path, monkeypatch, fake_registry):
    from fake_provider import FakeAdapter
    monkeypatch.setattr(FakeAdapter, "reports_usage", False)
    root, brief = project(tmp_path, monkeypatch, limits={"max_usage_tokens": 5000})
    with pytest.raises(PreflightError, match="does not report usage"):
        preflight(brief, root)


def test_every_final_state_gets_a_canonical_reason():
    base = {"failure": None, "human_gate": None}
    assert stop_reasons.derive({**base, "state": "COMPLETED"})["code"] == "completed"
    assert stop_reasons.derive({**base, "state": "FAILED", "failure": {"reason": "agent_committed", "detail": "x"}})["code"] == "safety_violation"
    assert stop_reasons.derive({**base, "state": "FAILED", "failure": {"reason": "reviewer_modified_worktree", "detail": "x"}})["code"] == "safety_violation"
    assert stop_reasons.derive({**base, "state": "FAILED", "failure": {"reason": "controller_error", "detail": "x"}})["code"] == "unknown_failure"
    assert stop_reasons.derive({**base, "state": "IMPLEMENTING"}) is None
    assert event_for({"state": "HUMAN_BLOCKED", "stop_reason": {"code": "runtime_budget_exhausted"}}) == "budget_exhausted"
    assert event_for({"state": "HUMAN_BLOCKED", "stop_reason": {"code": "validation_failure"}}) == "blocked"
