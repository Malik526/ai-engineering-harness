"""Decide, from brief metadata alone, whether an implementation may start autonomously.

This is the rollover gate: after a PASS, the controller evaluates the next
roadmap item here and either continues or stops and notifies. The decision is
driven by policy/autonomy.yaml; no model is consulted.
"""

from dataclasses import dataclass
from typing import Any, Iterable

from autobuild.policy.policy_loader import load_policy


@dataclass(frozen=True)
class GateDecision:
    """Outcome of the autonomy gate for one implementation."""

    implementation_id: str
    autonomy: str
    execution: str  # autonomous | prepare_only | prohibited (from the policy class)
    action: str  # continue | stop
    reasons: tuple[str, ...]

    @property
    def may_continue(self) -> bool:
        return self.action == "continue"


def evaluate_gate(
    meta: dict[str, Any],
    completed: Iterable[str],
    policy: dict[str, Any] | None = None,
) -> GateDecision:
    """Apply the autonomy policy to validated brief metadata.

    `completed` holds the ids of implementations already done, used for the
    dependency check.
    """
    policy = policy or load_policy("autonomy")
    autonomy = meta["autonomy"]
    execution = policy["classes"][autonomy]["execution"]
    conditions = policy["start_conditions"]
    done = set(completed)
    reasons: list[str] = []

    # --- Class ---
    if execution != "autonomous":
        reasons.append(f"autonomy class {autonomy} is {execution}")

    # --- Start conditions (apply to every class) ---
    if conditions["require_status_ready"] and meta["status"] != "ready":
        reasons.append(f"status is {meta['status']}, not ready")
    if conditions["require_dependencies_done"]:
        unmet = [dep for dep in meta["depends_on"] if dep not in done]
        if unmet:
            reasons.append("unmet dependencies: " + ", ".join(unmet))
    if conditions["require_no_human_requirements"] and meta["human_requirements"]:
        reasons.append("human requirements: " + "; ".join(meta["human_requirements"]))
    if conditions["require_no_external_requirements"] and meta["external_requirements"]:
        reasons.append("external requirements: " + "; ".join(meta["external_requirements"]))
    if conditions["require_no_human_validation"] and meta["validation"]["human_validation_required"]:
        reasons.append("acceptance requires human validation")

    return GateDecision(
        implementation_id=meta["id"],
        autonomy=autonomy,
        execution=execution,
        action="stop" if reasons else "continue",
        reasons=tuple(reasons),
    )
