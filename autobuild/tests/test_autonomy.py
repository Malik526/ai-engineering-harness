"""Autonomy gate decisions."""

from autobuild.autonomy import evaluate_gate
from helpers import example_brief


def test_green_ready_with_no_dependencies_continues():
    meta, _ = example_brief("EX-1-green.md")
    decision = evaluate_gate(meta, completed=[])
    assert decision.may_continue and decision.reasons == ()


def test_green_with_unmet_dependency_stops():
    meta, _ = example_brief("EX-1-green.md")
    meta["depends_on"] = ["EX-0"]
    decision = evaluate_gate(meta, completed=[])
    assert decision.action == "stop"
    assert any("EX-0" in r for r in decision.reasons)
    assert evaluate_gate(meta, completed=["EX-0"]).may_continue


def test_green_draft_stops():
    meta, _ = example_brief("EX-1-green.md")
    meta["status"] = "draft"
    assert not evaluate_gate(meta, completed=[]).may_continue


def test_yellow_stops_prepare_only_even_when_dependencies_done():
    meta, _ = example_brief("EX-2-yellow.md")
    decision = evaluate_gate(meta, completed=["EX-1"])
    assert decision.action == "stop"
    assert decision.execution == "prepare_only"


def test_red_is_prohibited():
    meta, _ = example_brief("EX-3-red.md")
    decision = evaluate_gate(meta, completed=[])
    assert decision.execution == "prohibited" and not decision.may_continue


def test_policy_is_data_driven():
    meta, _ = example_brief("EX-1-green.md")
    policy = {
        "classes": {"green": {"execution": "prohibited", "may_roll_over": False}},
        "start_conditions": dict.fromkeys(
            ["require_status_ready", "require_dependencies_done", "require_no_human_requirements",
             "require_no_external_requirements", "require_no_human_validation"], True),
    }
    assert not evaluate_gate(meta, completed=[], policy=policy).may_continue
