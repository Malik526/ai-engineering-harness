"""Render a notification payload as phone-readable text using templates/notification.md."""

import re
from string import Template
from typing import Any

from autobuild.paths import TEMPLATE_DIR

_LEADING_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)


def _bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"• {item}" for item in items) if items else empty


def _validation_text(v: dict[str, Any]) -> str:
    lines = [
        f"{v['tests_passed']} tests passed, {v['tests_failed']} failed",
        f"{v['browser_checks_passed']} browser checks passed, {v['browser_checks_failed']} failed",
    ]
    if v["failed_commands"]:
        lines.append("Failed: " + ", ".join(v["failed_commands"]))
    if not v["authoritative"]:
        lines.append("(reported by the implementer, not re-run by the controller)")
    return "\n".join(lines)


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
        status=payload["status"],
        summary=payload["summary"] or "—",
        validation=_validation_text(payload["validation"]),
        review=_review_text(payload["review"]),
        fixes=_bullets(payload["review"]["fixes"], "None"),
        branch=payload["branch"] or "—",
        commit=payload["commit"] or "—",
        next_step=_next_text(payload["next_step"]),
        human_action=_bullets(payload["human_action"], "None"),
        protected=f"{', '.join(protected['names'])}: {'MODIFIED' if protected['modified'] else 'unchanged'}",
    )
