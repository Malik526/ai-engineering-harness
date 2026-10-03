"""Notification decision, payload derivation, and rendering."""

import io

import pytest

from autobuild.autonomy import evaluate_gate
from autobuild.console_notifier import ConsoleNotifier
from autobuild.notification_payload import PayloadError, build_notification
from autobuild.notifier import should_notify
from autobuild.states import RunState
from helpers import example_brief, example_json


def _payload(**overrides):
    green, _ = example_brief("EX-1-green.md")
    yellow, _ = example_brief("EX-2-yellow.md")
    kwargs = dict(
        project="Content Automation",
        run_state=example_json("run-state.json"),
        implementation=green,
        summary="Caption length is now checked at scheduling time.",
        validation=example_json("validation.json"),
        reviews=[example_json("review-02-pass.json"), example_json("review-01-revise.json")],
        next_implementation=yellow,
        next_decision=evaluate_gate(yellow, completed=["EX-1"]),
        protected_branches=["main"],
        protected_branches_modified=False,
    )
    kwargs.update(overrides)
    return build_notification(**kwargs)


def test_should_notify_only_on_entering_notable_states():
    assert should_notify(RunState.REVIEWING, RunState.PASSED)
    assert not should_notify(RunState.PASSED, RunState.PASSED)
    assert not should_notify(RunState.VALIDATING, RunState.REVIEWING)


def test_payload_derived_from_structured_data():
    payload = _payload()
    assert payload["validation"] == {
        "authoritative": True, "tests_passed": 37, "tests_failed": 0,
        "browser_checks_passed": 0, "browser_checks_failed": 0, "failed_commands": [],
    }
    # Reviews are ordered by cycle regardless of input order.
    assert payload["review"]["initial_status"] == "REVISE"
    assert payload["review"]["final_status"] == "PASS"
    assert payload["review"]["fixes"] == ["Add exact-limit and limit + 1 boundary tests"]
    assert payload["next_step"]["action"] == "stop"
    assert "Register the OAuth redirect URI" in payload["human_action"]


def test_implementer_reported_validation_is_not_authoritative():
    validation = example_json("validation.json")
    validation["producer"] = "implementer"
    assert _payload(validation=validation)["validation"]["authoritative"] is False


def test_no_next_item():
    payload = _payload(next_implementation=None, next_decision=None)
    assert payload["next_step"]["action"] == "none" and payload["human_action"] == []


def test_invalid_payload_raises():
    with pytest.raises(PayloadError):
        _payload(protected_branches=[])


def test_console_rendering():
    stream = io.StringIO()
    ConsoleNotifier(stream).send(_payload())
    text = stream.getvalue()
    assert text.startswith("Content Automation Autonomous Build — EX-1 PASSED")
    assert "37 tests passed, 0 failed" in text
    assert "EX-2 — autonomy YELLOW" in text
    assert "main: unchanged" in text
    assert "<!--" not in text
