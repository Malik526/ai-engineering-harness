"""Completion summary shown at the end of every run and saved as report.md.

Built from controller-observed data; the implementer's report contributes only
its `known_issues`, labelled as reported.
"""

from typing import Any, Optional

_MAX_FILES = 25


def next_step(state: dict[str, Any], plan: Any) -> str:
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
        return (f"Inspect {worktree} and {plan.run_dir}/logs ({detail}). " +
                (f"Fix the cause, then explicitly run autobuild resume {plan.run_dir}." if state.get("failure", {}).get("recoverable")
                 else "Non-recoverable safety failure; human investigation is required."))
    if s == "STOPPED":
        return f"Run stopped; worktree {worktree} is preserved. Explicit resume: autobuild resume {plan.run_dir}."
    return f"Unexpected final state {s}; inspect {plan.run_dir}."


def _budget_lines(state: dict[str, Any], plan: Any) -> list[str]:
    """Every governance counter against its limit, from controller records only."""
    from autobuild.governance.governance import MINUTE, runtime_used, usage_used
    from autobuild.rollover.rollover_policy import settings
    limits = plan.config.data["limits"]
    record = state.get("governance")
    if not record:
        return []

    def of(used: Any, limit: Any) -> str:
        return f"{used}/{limit}" if limit is not None else f"{used} (no limit)"
    attempts = len(state.get("revision_history", []))
    executed = sum(1 for r in state.get("rollover_history", []) if r["status"] == "executed")
    minutes = round(runtime_used(record) / MINUTE, 2)
    runtime_limit = f"{limits['max_runtime_minutes']} min" if limits.get("max_runtime_minutes") else None
    unreported = sum(1 for op in record["operations"] if op["provider"] and op["usage"] is None)
    budget = [
        f"runtime {of(f'{minutes} min', runtime_limit)}",
        f"revisions {of(max(0, attempts - 1), limits.get('max_revision_attempts'))}",
        f"review cycles {of(state['review_cycle'], limits['max_review_cycles'])}",
        f"rollovers {of(executed, settings(plan.config.data)['max_rollovers'])}",
        f"validation runs {of(len(state.get('validation_history', [])), limits.get('max_validation_attempts'))}",
        f"browser runs {of(len(state.get('browser_history', [])), limits.get('max_browser_attempts'))}",
        f"tokens {of(usage_used(record), limits.get('max_usage_tokens'))}"
        + (f" ({unreported} agent operation(s) reported no usage)" if unreported else ""),
    ]
    by_kind: dict[str, float] = {}
    by_provider: dict[str, float] = {}
    for op in record["operations"]:
        by_kind[op["kind"]] = by_kind.get(op["kind"], 0) + op["duration_seconds"]
        if op["provider"]:
            by_provider[op["provider"]] = by_provider.get(op["provider"], 0) + op["duration_seconds"]
    time = "; ".join(f"{k} {round(v)}s" for k, v in by_kind.items()) or "no operations"
    providers = "; ".join(f"{k} {round(v)}s" for k, v in by_provider.items())
    lines = ["Budgets: " + "; ".join(budget), f"Time: {time}" + (f" (by provider: {providers})" if providers else "")]
    if record["overrides"]:
        lines.append("Limit overrides: " + "; ".join(f"{c['key']} {c['from']} -> {c['to']} at {o['at']}"
                                                     for o in record["overrides"] for c in o["changes"]))
    return lines


def _implementer_line(state: dict[str, Any], plan: Any) -> str:
    sessions = [s for s in state.get("agent_sessions", []) if s["role"] == "implementer"]
    active = sessions[-1]["provider"] if sessions else plan.assignment.provider
    executed = [r for r in state.get("rollover_history", []) if r["status"] == "executed"]
    origin = f" (took over from {executed[-1]['from_provider']} by rollover)" if executed else ""
    return f"Implementer: {active}{origin}"


def format_report(state: dict[str, Any], result: Optional[dict[str, Any]], evidence: Any,
                  validation: Any, plan: Any) -> str:
    lines = [
        f"Implementation: {plan.meta['id']} — {plan.meta['title']}",
        _implementer_line(state, plan),
        f"Reviewer: {(plan.reviewer_assignment.provider if plan.reviewer_assignment else '—')} (fresh session each cycle)",
        f"Status: {state['state']}" + (f" ({state['failure']['reason']})" if state.get("failure") else ""),
        *([f"Stop reason: {state['stop_reason']['code']} — {state['stop_reason']['detail']}"]
          if state.get("stop_reason") else []),
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
    rollovers = state.get("rollover_history", [])
    if rollovers:
        executed = sum(1 for r in rollovers if r["status"] == "executed")
        lines.append(f"Rollovers: {executed} executed of {len(rollovers)} recorded")
        lines += [f"  #{r['index']} {r['from_provider']} -> {r['to_provider'] or 'none'} ({r['failure']['kind']}): "
                  f"{r['status']}; {r['reason']}; handoff {plan.run_dir / r['handoff_artifact']}" for r in rollovers]
    lines += _budget_lines(state, plan)
    if state.get("review_mode") == "independent":
        lines.append(f"Independent review: {state.get('final_review_status') or 'not decided'}; cycles: {state['review_cycle']}")
    for browser in state.get("browser_history", []):
        lines.append(f"Browser attempt {browser['attempt']} (controller): "
                     f"{'PASSED' if browser['passed'] else 'NOT PASSED'}; evidence: {plan.run_dir / browser['artifact']}")
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
    lines.append(f"Human next step: {next_step(state, plan)}")
    return "\n".join(lines) + "\n"
