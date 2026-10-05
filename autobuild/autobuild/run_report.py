"""Completion summary shown at the end of every run and saved as report.md.

Built from controller-observed data; the implementer's report contributes only
its `known_issues`, labelled as reported.
"""

from typing import Any, Optional

_MAX_FILES = 25


def _next_step(state: dict[str, Any], plan: Any) -> str:
    s = state["state"]
    worktree = state.get("worktree") or plan.worktree
    if s == "COMPLETED" and state.get("last_commit"):
        return (f"Review {state['branch']} (commit {state['last_commit'][:12]}) in {worktree}; "
                f"diff: {plan.run_dir}/implementation/diff.patch. Merging is yours.")
    if s == "COMPLETED":
        return f"Review the uncommitted changes in {worktree} (checkpoint commits are disabled in the project config)."
    if s == "HUMAN_BLOCKED":
        return "; ".join(state["human_gate"]["human_action"])
    if s == "FAILED":
        detail = state["failure"]["detail"] if state.get("failure") else ""
        return (f"Inspect {worktree} and {plan.run_dir}/logs ({detail}). "
                "Fix the cause, then start a new run; the worktree is kept until you remove it.")
    if s == "STOPPED":
        return f"Run stopped; worktree {worktree} and its changes are preserved."
    return f"Unexpected final state {s}; inspect {plan.run_dir}."


def format_report(state: dict[str, Any], result: Optional[dict[str, Any]], evidence: Any,
                  validation: Any, plan: Any) -> str:
    lines = [
        f"Implementation: {plan.meta['id']} — {plan.meta['title']}",
        f"Provider: {plan.assignment.provider} ({plan.assignment.display_name})",
        f"Status: {state['state']}" + (f" ({state['failure']['reason']})" if state.get("failure") else ""),
        f"Branch: {state.get('branch') or '—'} (from {plan.base_branch} @ {plan.base_commit[:12]})",
        f"Worktree: {state.get('worktree') or '—'}",
        f"Run artifacts: {plan.run_dir}",
    ]
    if evidence is not None:
        paths = [f"{s} {p}" for s, p in evidence.changed]
        lines.append(f"Files changed: {len(paths)}")
        lines += [f"  {p}" for p in paths[:_MAX_FILES]]
        if len(paths) > _MAX_FILES:
            lines.append(f"  … {len(paths) - _MAX_FILES} more in implementation/changed-files.txt")
    else:
        lines.append("Files changed: not captured")
    if validation is not None:
        verdict = "PASSED" if validation.passed else "FAILED (" + ", ".join(validation.failed_required) + ")"
        lines.append(f"Validation (controller): {verdict}")
        lines += [f"  {c['name']}: {c['status']}" for c in validation.document["commands"]]
    else:
        lines.append("Validation (controller): not run")
    if state.get("last_commit"):
        lines.append(f"Commit: {state['last_commit'][:12]} (controller checkpoint; not pushed or merged)")
    else:
        reason = (state.get("checkpoint") or {}).get("reason")
        lines.append("Commit: none" + (f" ({reason})" if reason else ""))
    issues = (result or {}).get("reported") or {}
    known = issues.get("known_issues", []) if isinstance(issues, dict) else []
    lines.append("Known issues (reported by implementer): " + ("; ".join(known) if known else "none"))
    if result is not None and result["report_status"] != "valid":
        lines.append(f"Implementer report: {result['report_status']} ({result['report_error']})")
    lines.append(f"Human next step: {_next_step(state, plan)}")
    return "\n".join(lines) + "\n"
