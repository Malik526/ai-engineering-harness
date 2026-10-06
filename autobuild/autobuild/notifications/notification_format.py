"""Render a notification payload as phone-readable text using templates/notification.md."""

import re
from string import Template
from typing import Any

from autobuild.common.paths import TEMPLATE_DIR

_LEADING_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)


def _bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"• {item}" for item in items) if items else empty


_EVENT_TITLES = {
    "completed": "COMPLETED", "failed": "FAILED", "blocked": "BLOCKED", "stopped": "STOPPED",
    "human_action_required": "NEEDS YOU", "budget_exhausted": "BUDGET STOP", "rollover": "PROVIDER ROLLOVER",
}


def _validation_text(v: dict[str, Any]) -> str:
    lines = [f"{v['commands_passed']} validation command(s) passed, {v['commands_failed']} failed"]
    if v["failed_commands"]:
        lines.append("Failed: " + ", ".join(v["failed_commands"]))
    if not v["authoritative"]:
        lines.append("(reported by the implementer, not re-run by the controller)")
    return "\n".join(lines)


def _browser_text(b: Any) -> str:
    if b is None:
        return "No browser gates"
    verdict = "PASSED" if b["passed"] else "NOT PASSED"
    return f"{verdict} ({b['gates_passed']} gates passed, {b['gates_failed']} failed)"


def _review_text(r: dict[str, Any]) -> str:
    if r["cycles"] == 0:
        return "Not reviewed"
    return f"Initial: {r['initial_status']}\nFinal: {r['final_status']}\nCycles: {r['cycles']}"


def _next_text(n: dict[str, Any]) -> str:
    if n["action"] == "none":
        return "No further roadmap item queued."
    head = f"{n['implementation_id']} — autonomy {n['autonomy'].upper()}"
    verdict = "Autonomous execution continuing." if n["action"] == "continue" else "Stopped: " + "; ".join(n["reasons"])
    return f"{head}\n{verdict}"


def format_notification(payload: dict[str, Any]) -> str:
    """Fill templates/notification.md (minus its leading comment) from `payload`."""
    template = _LEADING_COMMENT.sub("", (TEMPLATE_DIR / "notification.md").read_text())
    protected = payload["protected_branches"]
    return Template(template).substitute(
        project=payload["project"],
        implementation_id=payload["implementation"]["id"],
        implementation_title=payload["implementation"]["title"],
        event_title=_EVENT_TITLES[payload["event"]],
        status=payload["status"],
        stop_reason=(f"\nStop reason: {payload['stop_reason']['code']} — {payload['stop_reason']['detail']}"
                     if payload["stop_reason"] else ""),
        summary=payload["summary"] or "—",
        implementer=payload["providers"]["implementer"] or "—",
        reviewer=payload["providers"]["reviewer"] or "—",
        attempts=payload["counts"]["implementation_attempts"],
        cycles=payload["counts"]["review_cycles"],
        rollovers=payload["counts"]["rollovers"],
        validation=_validation_text(payload["validation"]),
        browser=_browser_text(payload["browser"]),
        review=_review_text(payload["review"]),
        fixes=_bullets(payload["review"]["fixes"], "None"),
        branch=payload["branch"] or "—",
        commit=payload["commit"] or "—",
        next_step=_next_text(payload["next_step"]),
        human_action=_bullets(payload["human_action"], "None"),
        protected=f"{', '.join(protected['names'])}: {'MODIFIED' if protected['modified'] else 'unchanged'}",
    )
