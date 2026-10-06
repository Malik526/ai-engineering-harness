"""Evidence-first independent review and findings-only revision prompts.

Identity and workflow decisions belong to the controller. Agent narrative is
explicitly supplemental and follows the frozen brief and Git/validation evidence.
"""

import json


def review_prompt(plan, store, cycle: int, attempt: int, session_id: str) -> str:
    prefix = f"implementation/cycle-{attempt:02d}"
    blocks = [
        "# Independent Review",
        "You are a fresh, read-only reviewer. Do not modify files, run builds, commit, or invoke external actions.",
        "Inspect authoritative evidence first. Judge the implementation, not the implementer's claims.",
        f"Run: {plan.run_id}; implementation: {plan.meta['id']}; cycle: {cycle}.",
        f"Reviewer provider: {plan.reviewer_assignment.provider}; provisional session: {session_id}.",
        f"Worktree: {plan.worktree}. Global policies: ~/.agents/*.md. This is an Autobuild reviewer session.",
        "## Approved Brief\n" + store.path("brief.md").read_text(),
        "## Actual Git Diff\n" + store.path(f"{prefix}/diff.patch").read_text(),
        "## Changed Files\n" + store.path(f"{prefix}/changed-files.txt").read_text(),
        "## Git Snapshot\n" + store.path(f"{prefix}/git.json").read_text(),
        "## Controller Validation\n" + store.path(f"validation/cycle-{attempt:02d}/results.json").read_text(),
        "## Project Context",
        "Read relevant project instructions and architecture/ADRs in the worktree before deciding:",
        ", ".join(["AGENTS.md and other project-local instruction files", "README.md", "docs/ARCHITECTURE.md",
                   plan.config.data["paths"]["project_state"], plan.config.data["paths"]["adr_directory"]]),
        "Validation stdout/stderr paths are relative to " + str(plan.run_dir) + ". Read critical results as needed.",
        "Required deterministic validation is a hard checkpoint gate. Use REVISE for a fixable FAIL and BLOCK for "
        "ERROR, unavailable confinement/tooling, malformed setup, or unverifiable evidence. Never override non-PASS evidence.",
        "Return exactly one structured review: PASS, REVISE, or BLOCK. Legacy BLOCKED is accepted as BLOCK.",
        "REVISE findings must identify requirement, severity, evidence, affected files/locations and required correction.",
        "Use BLOCK for human prerequisites, conflicting requirements, unsafe actions or unverifiable critical requirements.",
        "evidence_reviewed must include brief, git_diff, changed_files and validation_output. List other evidence actually read.",
        "Use the run/implementation/cycle above. Return the existing review schema. The controller records actual identity and time.",
        f"reviewed_at must be a full ISO-8601 timestamp, for example {store.state['updated_at']}. Finding IDs use R{cycle}-1, R{cycle}-2, etc.",
        "## Supplemental Implementer Narrative (Read Last)\n" + store.path(f"{prefix}/summary.md").read_text(),
    ]
    executed = [r for r in store.state.get("rollover_history", []) if r["status"] == "executed"]
    if executed:
        record = executed[-1]
        blocks.insert(6, f"Rollover (controller record): {record['from_provider']} stopped with "
                         f"{record['failure']['kind']}; a new {record['to_provider']} session took over through "
                         f"{plan.run_dir / record['handoff_artifact']}. Judge the current diff as one implementation; "
                         "neither implementer's narrative is evidence.")
    browser = store.path(f"browser/cycle-{attempt:02d}/results.json")
    if browser.is_file():
        document = json.loads(browser.read_text())
        summary = {key: value for key, value in document.items() if key != "files"}
        anchor = next(i for i, block in enumerate(blocks) if block.startswith("## Controller Validation"))
        blocks.insert(anchor, "## Controller Browser Evidence\n" + json.dumps(summary, indent=2)
                      + "\nImmutable manifest and raw artifacts: " + str(browser)
                      + "\nInclude browser_evidence in evidence_reviewed. Required gates must PASS; "
                        "use REVISE for fixable FAIL and BLOCK for unavailable tools or missing coverage.")
    return "\n\n".join(blocks) + "\n"


def revision_prompt(plan, store, review: dict | None) -> str:
    blocks = ["# Continue Approved Implementation",
              f"Work only in {plan.worktree}, branch {plan.branch}. Leave changes uncommitted; the controller owns Git.",
              "Continue the existing implementer session. Do not invoke a reviewer or Autobuild yourself.",
              "Resolve only the required findings and necessary documentation. The frozen approved brief remains authoritative.",
              "Frozen brief: " + str(store.path("brief.md")),
              "The controller reruns validation and starts a fresh reviewer after your corrections."]
    if review:
        blocks.append("## Required Review Findings\n" + json.dumps({
            "cycle": review["cycle"], "findings": review["findings"],
            "blocked_reason": review.get("blocked_reason"),
        }, indent=2))
    else:
        blocks.append("Continue the interrupted or failed implementation using the approved brief and preserved worktree.")
    if store.state.get("browser_history"):
        blocks.append("Controller browser evidence (read the failures and preserved logs): "
                      + str(store.path(store.state["browser_history"][-1]["artifact"])))
    blocks.append("Return the implementation-report schema, with implementation_summary, files_changed, tests_reported, "
                  "documentation_changed, assumptions and known_issues.")
    return "\n\n".join(blocks) + "\n"
