"""The one canonical reviewer contract, independent of which provider reviewed.

Adapters only change the wire syntax (their own schema projection) and
validate answers against schemas/review.schema.json. `normalize_review` then
applies the controller's semantic rules and turns any provider's answer into the
same persisted review: PASS / REVISE / BLOCK with controller-observed identity.
"""

from typing import Any, Optional

from autobuild.schemas import schema_errors

REQUIRED_EVIDENCE = frozenset({"brief", "git_diff", "changed_files", "validation_output"})


def normalize_review(raw: Any, *, run_id: str, implementation_id: str, cycle: int, provider: str,
                     session_id: str, reviewed_at: str, browser_evidence: bool) -> tuple[Optional[dict], list[str]]:
    """Return (canonical review, []) or (None, errors). Identity and time come from the controller."""
    if not isinstance(raw, dict):
        return None, ["reviewer returned no structured review"]
    review = dict(raw)
    errors = schema_errors("review", review)
    if errors:
        return None, errors
    if (review["run_id"], review["implementation_id"], review["cycle"]) != (run_id, implementation_id, cycle):
        errors.append("review identity does not match the current run/cycle")
    if not REQUIRED_EVIDENCE <= set(review["evidence_reviewed"]):
        errors.append("required authoritative evidence is missing")
    if browser_evidence and "browser_evidence" not in review["evidence_reviewed"]:
        errors.append("controller browser evidence was not reviewed")
    findings = review["findings"]
    if len({finding["id"] for finding in findings}) != len(findings):
        errors.append("finding IDs are not unique")
    if errors:
        return None, errors
    review.update(reviewer={"provider": provider, "session_id": session_id}, reviewed_at=reviewed_at)
    if review["status"] == "BLOCKED":
        review["status"] = "BLOCK"
    return review, []
