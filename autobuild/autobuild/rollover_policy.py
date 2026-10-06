"""Bounded implementer rollover: when a provider/session failure may hand the work to another session.

Pure decisions over the frozen project config. A rollover needs all of:
- an eligible failure kind (provider_failures.ROLLOVER_ELIGIBLE) listed in `rollover.on`;
- remaining budget (`rollover.max_rollovers`, at most 1 in 0.6);
- an allowed transition: the replacement is listed in `rollover.implementer`,
  supports the implementer role, and differs from the failed provider unless
  the failure was session-scoped;
- a replacement that passes its health check now.
Anything else blocks for a human. Nothing here picks a provider that is not configured.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from autobuild.provider_failures import PROVIDER_SCOPED, ROLLOVER_ELIGIBLE, ProviderFailure
from autobuild.roles import IMPLEMENTER

HealthCheck = Callable[[str], tuple[bool, str]]


@dataclass(frozen=True)
class RolloverDecision:
    allowed: bool
    replacement: Optional[str]
    reason: str


def settings(config_data: dict[str, Any]) -> dict[str, Any]:
    """The rollover block with defaults; an absent block means a budget of 0."""
    configured = config_data.get("rollover")
    if not configured:
        return {"max_rollovers": 0, "approval": "human", "implementer": [], "on": sorted(ROLLOVER_ELIGIBLE)}
    return {**configured, "on": configured.get("on", sorted(ROLLOVER_ELIGIBLE))}


def rollover_config_errors(config_data: dict[str, Any], providers: dict[str, Any]) -> list[str]:
    errors = []
    for provider in (config_data.get("rollover") or {}).get("implementer", []):
        if provider not in providers:
            errors.append(f"rollover.implementer: unknown provider {provider!r}")
        elif IMPLEMENTER not in providers[provider]["roles"]:
            errors.append(f"rollover.implementer: provider {provider!r} does not support the implementer role")
    return errors


def transition_error(config_data: dict[str, Any], kind: str, from_provider: str, to_provider: str) -> Optional[str]:
    """Why from -> to is not an allowed transition for a failure of `kind`, or None."""
    policy = settings(config_data)
    if kind not in ROLLOVER_ELIGIBLE or kind not in policy["on"]:
        return f"{kind} is not a configured rollover trigger"
    if to_provider not in policy["implementer"]:
        return f"{to_provider} is not a configured rollover implementer"
    if to_provider == from_provider and kind in PROVIDER_SCOPED:
        return f"{from_provider} cannot replace itself after a provider-wide {kind}"
    return None


def decide(config_data: dict[str, Any], failure: ProviderFailure, failed_provider: str, executed: int,
           health: HealthCheck) -> RolloverDecision:
    policy = settings(config_data)
    if not failure.rollover_eligible:
        return RolloverDecision(False, None, f"{failure.kind} is not a rollover trigger")
    if policy["max_rollovers"] == 0:
        return RolloverDecision(False, None, "rollover is not configured for this project")
    if failure.kind not in policy["on"]:
        return RolloverDecision(False, None, f"rollover is not configured for {failure.kind}")
    if executed >= policy["max_rollovers"]:
        return RolloverDecision(False, None, f"rollover budget exhausted ({executed}/{policy['max_rollovers']})")
    rejected, unavailable = [], []
    for candidate in policy["implementer"]:
        problem = transition_error(config_data, failure.kind, failed_provider, candidate)
        if problem:
            rejected.append(problem)
            continue
        available, detail = health(candidate)
        if not available:
            unavailable.append(f"{candidate} unavailable ({detail})")
            continue
        return RolloverDecision(True, candidate,
                                f"{failed_provider} {failure.kind}; configured rollover selects {candidate}")
    if unavailable:
        return RolloverDecision(False, None, "no configured replacement implementer is available: " + "; ".join(unavailable))
    return RolloverDecision(False, None, "unsupported provider transition: " + "; ".join(rejected))
