"""Canonical stop reasons: one code says why a run ended, independent of its final state.

The state machine says *where* a run stopped (COMPLETED, HUMAN_BLOCKED, FAILED,
STOPPED); `state.stop_reason` says *why*. Governance and rollover set codes
explicitly; everything else is derived here from the recorded failure, so a
provider failure is never confused with an exhausted budget.
"""

from typing import Any, Optional

COMPLETED = "completed"
HUMAN_BLOCKED = "human_blocked"  # a reviewer BLOCK or prepared rollover awaiting approval
REMOTE_STOP = "remote_stop"
INTERRUPTED = "interrupted"  # operator Ctrl-C on the controller
RUNTIME_BUDGET = "runtime_budget_exhausted"
REVIEW_BUDGET = "review_budget_exhausted"
REVISION_BUDGET = "revision_budget_exhausted"
ROLLOVER_BUDGET = "rollover_budget_exhausted"
USAGE_BUDGET = "usage_budget_exhausted"
VALIDATION_BUDGET = "validation_budget_exhausted"
BROWSER_BUDGET = "browser_budget_exhausted"
PROVIDER_FAILURE = "provider_failure"
VALIDATION_FAILURE = "validation_failure"
BROWSER_FAILURE = "browser_failure"
SAFETY_VIOLATION = "safety_violation"
NO_CHANGES = "no_changes"
UNKNOWN_FAILURE = "unknown_failure"

BUDGET_CODES = frozenset({RUNTIME_BUDGET, REVIEW_BUDGET, REVISION_BUDGET, ROLLOVER_BUDGET, USAGE_BUDGET,
                          VALIDATION_BUDGET, BROWSER_BUDGET})
ALL_CODES = BUDGET_CODES | {COMPLETED, HUMAN_BLOCKED, REMOTE_STOP, INTERRUPTED, PROVIDER_FAILURE,
                            VALIDATION_FAILURE, BROWSER_FAILURE, SAFETY_VIOLATION, NO_CHANGES, UNKNOWN_FAILURE}

# FAILED runs: failure.reason -> canonical code. Anything unlisted is unknown_failure.
_FAILURE_CODES = {
    "provider_failed": PROVIDER_FAILURE, "provider_timeout": PROVIDER_FAILURE, "reviewer_failed": PROVIDER_FAILURE,
    "reviewer_unavailable": PROVIDER_FAILURE, "invalid_review": PROVIDER_FAILURE,
    "implementer_resume_mismatch": PROVIDER_FAILURE, "reviewer_session_reused": SAFETY_VIOLATION,
    "no_changes": NO_CHANGES,
    "protected_branch_modified": SAFETY_VIOLATION, "agent_committed": SAFETY_VIOLATION,
    "branch_changed": SAFETY_VIOLATION, "worktree_mismatch": SAFETY_VIOLATION,
    "secret_like_files": SAFETY_VIOLATION, "frozen_brief_modified": SAFETY_VIOLATION,
    "browser_evidence_modified": SAFETY_VIOLATION, "validation_evidence_modified": SAFETY_VIOLATION,
    "rollover_handoff_invalid": SAFETY_VIOLATION,
}


def derive(state: dict[str, Any]) -> Optional[dict[str, Any]]:
    """A stop reason for a finished run whose code was not set explicitly; None while it is still running."""
    final = state["state"]
    if final == "COMPLETED":
        return {"code": COMPLETED, "detail": "independent review passed; controller evidence passed", "limit": None}
    if final == "FAILED":
        failure = state["failure"]
        reason = failure["reason"]
        code = _FAILURE_CODES.get(reason)
        if code is None and reason.endswith(("_modified_worktree", "_git_changed")):
            code = SAFETY_VIOLATION
        return {"code": code or UNKNOWN_FAILURE, "detail": f"{reason}: {failure['detail']}", "limit": None}
    if final == "HUMAN_BLOCKED":
        return {"code": HUMAN_BLOCKED, "detail": state["human_gate"]["reason"], "limit": None}
    if final == "STOPPED":
        return {"code": INTERRUPTED, "detail": "controller interrupted", "limit": None}
    return None
