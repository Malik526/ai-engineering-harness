"""Build the notification payload from structured run data only.

Inputs are the documents the controller already holds (state, brief metadata,
validation and browser results, reviews, the next gate decision); nothing here
reads agent narrative except the one-line `summary` the caller chooses to pass.
`run_payload` derives every field of a run's notification from its run
directory, so the controller never composes notification text itself.
"""

import json
from pathlib import Path
from typing import Any, Optional, Sequence

from autobuild.policy.autonomy import GateDecision
from autobuild.common.schemas import schema_errors
from autobuild.governance.stop_reasons import BUDGET_CODES, HUMAN_BLOCKED


class PayloadError(ValueError):
    """The assembled payload does not satisfy notification.schema.json."""


def _validation_counts(validation: Optional[dict[str, Any]]) -> dict[str, Any]:
    counts = {"authoritative": False, "commands_passed": 0, "commands_failed": 0, "failed_commands": []}
    if validation is None:
        return counts
    counts["authoritative"] = validation["producer"] == "controller"
    for command in validation["commands"]:
        status = command.get("status")
        if status is None:  # schema v1: exit code is the only verdict
            status = "PASS" if command["exit_code"] == 0 else "FAIL"
        if status.upper() in ("PASS", "SKIPPED", "PASSED"):
            counts["commands_passed"] += status.upper() != "SKIPPED"
        else:
            counts["commands_failed"] += 1
            counts["failed_commands"].append(command["name"])
    return counts


def _browser_counts(browser: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if browser is None:
        return None
    gates = browser.get("gates", [])
    passed = sum(1 for gate in gates if gate["status"] == "PASS")
    return {"passed": bool(browser["passed"]), "gates_passed": passed,
            "gates_failed": sum(1 for gate in gates if gate["status"] in ("FAIL", "ERROR"))}


def _review_summary(reviews: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(reviews, key=lambda r: r["cycle"])
    # Corrections requested before the final review are the fixes made during review.
    fixes = [f["required_correction"] for r in ordered[:-1] for f in r["findings"]]
    return {
        "cycles": len(ordered),
        "initial_status": ordered[0]["status"] if ordered else None,
        "final_status": ordered[-1]["status"] if ordered else None,
        "fixes": fixes,
    }


def event_for(state: dict[str, Any]) -> str:
    """The lifecycle event a finished run reports."""
    code = (state.get("stop_reason") or {}).get("code")
    final = state["state"]
    if final == "COMPLETED":
        return "completed"
    if final == "STOPPED":
        return "stopped"
    if final == "FAILED":
        return "failed"
    if code in BUDGET_CODES:
        return "budget_exhausted"
    return "human_action_required" if code == HUMAN_BLOCKED else "blocked"


def build_notification(
    *,
    project: str,
    run_state: dict[str, Any],
    implementation: dict[str, Any],
    summary: str,
    validation: Optional[dict[str, Any]],
    reviews: Sequence[dict[str, Any]],
    next_implementation: Optional[dict[str, Any]],
    next_decision: Optional[GateDecision],
    protected_branches: Sequence[str],
    protected_branches_modified: bool,
    event: Optional[str] = None,
    browser: Optional[dict[str, Any]] = None,
    providers: Optional[dict[str, Optional[str]]] = None,
) -> dict[str, Any]:
    """Assemble and validate a notification payload.

    `protected_branches_modified` must come from the controller comparing
    protected refs before and after the run.
    """
    human_action: list[str] = list((run_state.get("human_gate") or {}).get("human_action", []))
    if next_decision is not None and next_implementation is not None:
        next_step = {
            "implementation_id": next_decision.implementation_id,
            "autonomy": next_decision.autonomy,
            "action": next_decision.action,
            "reasons": list(next_decision.reasons),
        }
        if not next_decision.may_continue:
            human_action += [a for a in next_implementation["human_requirements"] if a not in human_action]
    else:
        next_step = {"implementation_id": None, "autonomy": None, "action": "none", "reasons": []}
    sessions = run_state.get("agent_sessions", [])
    latest = {role: next((s["provider"] for s in reversed(sessions) if s["role"] == role), None)
              for role in ("implementer", "reviewer")}
    stop = run_state.get("stop_reason")
    payload = {
        "run_id": run_state["run_id"],
        "project": project,
        "implementation": {"id": implementation["id"], "title": implementation["title"]},
        "event": event or event_for(run_state),
        "status": run_state["state"],
        "stop_reason": {"code": stop["code"], "detail": stop["detail"]} if stop else None,
        "summary": summary,
        "providers": providers or latest,
        "counts": {
            "implementation_attempts": len(run_state.get("revision_history", [])),
            "review_cycles": run_state.get("review_cycle", 0),
            "rollovers": sum(1 for r in run_state.get("rollover_history", []) if r["status"] == "executed"),
        },
        "validation": _validation_counts(validation),
        "browser": _browser_counts(browser),
        "review": _review_summary(reviews),
        "branch": run_state["branch"],
        "commit": run_state["last_commit"],
        "next_step": next_step,
        "human_action": human_action,
        "protected_branches": {"names": list(protected_branches), "modified": protected_branches_modified},
    }
    errors = schema_errors("notification", payload)
    if errors:
        raise PayloadError("; ".join(errors))
    return payload


def _latest(run_dir: Path, history: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    return json.loads((run_dir / history[-1]["artifact"]).read_text()) if history else None


def run_payload(*, run_dir: Path, state: dict[str, Any], project: str, implementation: dict[str, Any],
                protected_branches: Sequence[str], protected_now: dict[str, Optional[str]],
                summary: str, event: Optional[str] = None, next_action: Optional[str] = None,
                implementer: Optional[str] = None) -> dict[str, Any]:
    """A notification for a run, built only from its state and controller artifacts.

    `next_action` is the controller's own next-step text, used when the run has no human gate (e.g. STOPPED).
    `implementer` names the active implementer when it changed before its session exists (a rollover).
    """
    reviews = [json.loads((run_dir / r["artifact"]).read_text()) for r in state.get("review_history", [])]
    if next_action and not (state.get("human_gate") or {}).get("human_action"):
        state = {**state, "human_gate": {**(state.get("human_gate") or {}), "human_action": [next_action]}}
    sessions = state.get("agent_sessions", [])
    reviewer = next((s["provider"] for s in reversed(sessions) if s["role"] == "reviewer"), None)
    latest = next((s["provider"] for s in reversed(sessions) if s["role"] == "implementer"), None)
    return build_notification(
        providers={"implementer": implementer or latest, "reviewer": reviewer},
        project=project, run_state=state, implementation=implementation, summary=summary,
        validation=_latest(run_dir, state.get("validation_history", [])), reviews=reviews,
        next_implementation=None, next_decision=None, protected_branches=protected_branches,
        protected_branches_modified=protected_now != state.get("protected_refs", protected_now),
        event=event, browser=_latest(run_dir, state.get("browser_history", [])))
