"""Controller-owned run governance: budgets, runtime/usage accounting and stop decisions.

Every limit is deterministic and checked by the controller before it starts an
agent or tool operation (implementation, validation, browser, review). While a
provider runs, `watch` polls the stop controller and the runtime deadline from a
separate thread and terminates the provider's process group itself; no model is
asked to stop. Counters come from the run's own histories, so they survive
resume and are never reset silently.
"""

import copy
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from autobuild.rollover_policy import settings as rollover_settings
from autobuild.stop_reasons import (BROWSER_BUDGET, REMOTE_STOP, REVIEW_BUDGET, REVISION_BUDGET, RUNTIME_BUDGET,
                                    USAGE_BUDGET, VALIDATION_BUDGET)

MINUTE = 60.0  # seconds per configured runtime minute (tests shorten it)
POLL_SECONDS = 2.0  # how often a running operation is checked for stop/deadline

# Budgets a human may change on resume, only with an explicit override.
OVERRIDABLE_LIMITS = ("max_runtime_minutes", "max_review_cycles", "max_revision_attempts",
                      "max_validation_attempts", "max_browser_attempts", "max_usage_tokens")


def _monotonic() -> float:
    return time.monotonic()


@dataclass(frozen=True)
class StopDecision:
    code: str  # canonical stop reason (stop_reasons.py)
    detail: str
    limit: Optional[dict[str, Any]] = None  # {"name", "limit", "used"} for budget stops

    def as_record(self, at: str) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail, "limit": self.limit, "at": at}


def empty_record() -> dict[str, Any]:
    return {"segments": [], "operations": [], "overrides": []}


def usage_used(record: dict[str, Any]) -> int:
    return sum((op.get("usage") or {}).get("total_tokens", 0) for op in record["operations"])


def runtime_used(record: dict[str, Any]) -> float:
    return sum(segment["active_seconds"] for segment in record["segments"])


def _budget(name: str, limit: Optional[float], used: float, code: str, unit: str = "") -> Optional[StopDecision]:
    if limit is None or used < limit:
        return None
    shown = f"{round(used, 2)}{unit} of {limit}{unit}"
    return StopDecision(code, f"{name} exhausted ({shown})", {"name": name, "limit": limit, "used": round(used, 3)})


def budget_stop(config_data: dict[str, Any], state: dict[str, Any], kind: str,
                active_seconds: Optional[float] = None) -> Optional[StopDecision]:
    """The budget that forbids starting one more `kind` operation, if any."""
    limits, record = config_data["limits"], state.get("governance") or empty_record()
    minutes = limits.get("max_runtime_minutes")
    seconds = runtime_used(record) if active_seconds is None else active_seconds
    checks = [
        _budget("limits.max_runtime_minutes", minutes, seconds / MINUTE, RUNTIME_BUDGET, " min"),
        _budget("limits.max_usage_tokens", limits.get("max_usage_tokens"), usage_used(record), USAGE_BUDGET, " tokens"),
    ]
    attempts = len(state.get("revision_history", []))
    if kind == "implementation" and attempts >= 1:
        # Every implementer invocation after the first (resume, revision or rollover) is a revision attempt.
        checks.append(_budget("limits.max_revision_attempts", limits.get("max_revision_attempts"), attempts - 1,
                              REVISION_BUDGET))
    if kind == "validation":
        checks.append(_budget("limits.max_validation_attempts", limits.get("max_validation_attempts"),
                              len(state.get("validation_history", [])), VALIDATION_BUDGET))
    if kind == "browser":
        checks.append(_budget("limits.max_browser_attempts", limits.get("max_browser_attempts"),
                              len(state.get("browser_history", [])), BROWSER_BUDGET))
    if kind == "review":
        checks.append(_budget("limits.max_review_cycles", limits["max_review_cycles"], state["review_cycle"],
                              REVIEW_BUDGET))
    return next((check for check in checks if check is not None), None)


def exhausted_on_resume(config_data: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Budgets that would stop a resumed run before its first operation (resume always implements first)."""
    details = [decision.detail for kind in ("implementation", "review")
               for decision in [budget_stop(config_data, state, kind)] if decision is not None]
    return list(dict.fromkeys(details))  # run-wide budgets (runtime, tokens) apply to both kinds


def limit_changes(original: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    """Overridable budget differences between the frozen and current config."""
    changes = [{"key": f"limits.{key}", "from": original["limits"].get(key), "to": current["limits"].get(key)}
               for key in OVERRIDABLE_LIMITS if original["limits"].get(key) != current["limits"].get(key)]
    before, after = rollover_settings(original)["max_rollovers"], rollover_settings(current)["max_rollovers"]
    if before != after:
        changes.append({"key": "rollover.max_rollovers", "from": before, "to": after})
    return changes


def without_overridable(config_data: dict[str, Any]) -> dict[str, Any]:
    """Execution config with every overridable budget removed, for frozen-config comparison."""
    stripped = copy.deepcopy(config_data)
    for key in OVERRIDABLE_LIMITS:
        stripped["limits"].pop(key, None)
    if stripped.get("rollover"):
        stripped["rollover"].pop("max_rollovers", None)
    return stripped


def effective_config(original: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[str, Any]:
    """The frozen config with every recorded human override applied, in order."""
    effective = copy.deepcopy(original)
    for override in overrides:
        for change in override["changes"]:
            section, key = change["key"].split(".", 1)
            target = effective.setdefault(section, {}) or {}
            effective[section] = target
            if change["to"] is None:
                target.pop(key, None)
            else:
                target[key] = change["to"]
    return effective


def governance_config_errors(config_data: dict[str, Any]) -> list[str]:
    """Combinations that can never work, rejected before a run starts."""
    limits, errors = config_data["limits"], []
    rollovers = rollover_settings(config_data)["max_rollovers"]
    if rollovers and limits.get("max_revision_attempts") == 0:
        errors.append("limits.max_revision_attempts is 0, so a configured rollover could never run its replacement")
    if config_data["control"]["remote_stop_enabled"] and config_data["control"]["provider"] != "file":
        errors.append(f"control.provider {config_data['control']['provider']!r} is not implemented; use file")
    return errors


class Governor:
    """Live accounting for one controller session of a run."""

    def __init__(self, config_data: dict[str, Any], stop_controller: Any, run_id: str):
        self.config_data = config_data
        self.stop_controller = stop_controller
        self.run_id = run_id
        self.closed_seconds = 0.0
        self.session_start = _monotonic()
        self.interrupted: Optional[StopDecision] = None
        self.stop_request = None

    def start_segment(self, record: dict[str, Any]) -> None:
        self.closed_seconds = runtime_used(record)
        self.session_start = _monotonic()

    def session_seconds(self) -> float:
        return _monotonic() - self.session_start

    def active_seconds(self) -> float:
        return self.closed_seconds + self.session_seconds()

    def remote_stop(self) -> Optional[StopDecision]:
        if self.stop_controller is None:
            return None
        request = self.stop_controller.check_stop_requested(self.run_id)
        if request is None:
            return None
        self.stop_request = request
        reason = f": {request.reason}" if request.reason else ""
        return StopDecision(REMOTE_STOP, f"stop requested by {request.requested_by} at {request.requested_at}{reason}")

    def check(self, kind: str, state: dict[str, Any]) -> Optional[StopDecision]:
        return self.remote_stop() or budget_stop(self.config_data, state, kind, self.active_seconds())

    def _deadline_passed(self) -> Optional[StopDecision]:
        minutes = self.config_data["limits"].get("max_runtime_minutes")
        return _budget("limits.max_runtime_minutes", minutes, self.active_seconds() / MINUTE, RUNTIME_BUDGET, " min") \
            if minutes is not None else None

    @contextmanager
    def watch(self, adapter: Any) -> Iterator[None]:
        """Terminate `adapter`'s operation from outside if a stop is requested or runtime runs out."""
        self.interrupted = None
        done = threading.Event()

        def poll() -> None:
            while not done.wait(POLL_SECONDS):
                decision = self.remote_stop() or self._deadline_passed()
                if decision is not None:
                    self.interrupted = decision
                    adapter.terminate()
                    return

        thread = threading.Thread(target=poll, name="autobuild-governor", daemon=True)
        thread.start()
        try:
            yield
        finally:
            done.set()
            thread.join()
