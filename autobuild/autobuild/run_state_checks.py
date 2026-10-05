"""Run-state rules that JSON Schema cannot express on its own.

Some rules need the project config (protected branches, branch prefix,
review-cycle limit); others compare fields against each other.
"""

from datetime import datetime
from typing import Any

from autobuild.config import ProjectConfig
from autobuild.safety import is_protected_branch
from autobuild.schemas import schema_errors


def _parse_timestamp(value: str) -> datetime:
    # Python 3.10's fromisoformat does not accept a trailing 'Z'.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def run_state_errors(state: dict[str, Any], config: ProjectConfig | None = None) -> list[str]:
    """Schema errors, then semantic errors; config-dependent rules run only when `config` is given."""
    errors = schema_errors("run-state", state)
    if errors:
        return errors

    if _parse_timestamp(state["updated_at"]) < _parse_timestamp(state["started_at"]):
        errors.append("updated_at: earlier than started_at")

    # Independence: the reviewer must be a fresh session, never one the
    # implementer used — even when the same provider fills both roles.
    sessions = state["agent_sessions"]
    implementer_ids = {s["session_id"] for s in sessions if s["role"] == "implementer"}
    reused = sorted(s["session_id"] for s in sessions if s["role"] == "reviewer" and s["session_id"] in implementer_ids)
    if reused:
        errors.append("agent_sessions: reviewer reuses implementer session " + ", ".join(reused))
    reviewer_ids = [s["session_id"] for s in sessions if s["role"] == "reviewer"]
    if len(set(reviewer_ids)) != len(reviewer_ids):
        errors.append("agent_sessions: reviewer session reused across review cycles")
    if state.get("final_review_status") == "PASS" and not any(
            r.get("status") == "PASS" for r in state.get("review_history", [])):
        errors.append("final_review_status: PASS requires a persisted passing review")
    if "final_review_status" in state and state["state"] in ("PASSED", "COMPLETED") and state["review_mode"] == "independent":
        history = state.get("review_history", [])
        if (state["final_review_status"] != "PASS" or not history or history[-1]["status"] != "PASS"
                or history[-1]["cycle"] != state["review_cycle"]):
            errors.append("final_review_status: independent completion requires the latest cycle to PASS")

    if config is not None:
        branch = state["branch"]
        if branch is not None:
            if is_protected_branch(branch, config.protected_branches):
                errors.append(f"branch: {branch!r} is protected; runs must use an automation branch")
            elif not branch.startswith(config.branch_prefix):
                errors.append(f"branch: {branch!r} does not start with {config.branch_prefix!r}")
        if state["review_cycle"] > config.max_review_cycles:
            errors.append(f"review_cycle: {state['review_cycle']} exceeds limit {config.max_review_cycles}")

    return errors
