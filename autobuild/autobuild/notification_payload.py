"""Build the notification payload from structured run data only.

Inputs are the documents the controller already holds (state, brief metadata,
validation results, reviews, the next gate decision); nothing here reads agent
narrative except the one-line `summary` the caller chooses to pass through.
"""

from typing import Any, Optional, Sequence

from autobuild.autonomy import GateDecision
from autobuild.schemas import schema_errors


class PayloadError(ValueError):
    """The assembled payload does not satisfy notification.schema.json."""


def _validation_counts(validation: Optional[dict[str, Any]]) -> dict[str, Any]:
    counts = {"authoritative": False, "tests_passed": 0, "tests_failed": 0,
              "browser_checks_passed": 0, "browser_checks_failed": 0, "failed_commands": []}
    if validation is None:
        return counts
    counts["authoritative"] = validation["producer"] == "controller"
    for command in validation["commands"]:
        prefix = "browser_checks" if command["kind"] == "browser" else "tests"
        if command["kind"] in ("test", "browser"):
            counts[f"{prefix}_passed"] += command.get("passed", 0)
            counts[f"{prefix}_failed"] += command.get("failed", 0)
        if command["exit_code"] != 0:
            counts["failed_commands"].append(command["name"])
    return counts


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

    payload = {
        "run_id": run_state["run_id"],
        "project": project,
        "implementation": {"id": implementation["id"], "title": implementation["title"]},
        "status": run_state["state"],
        "summary": summary,
        "validation": _validation_counts(validation),
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
