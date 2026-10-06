"""Deterministic rollover handoff: freeze the run, hash what a replacement inherits, verify before takeover.

The replacement implementer never depends on another provider's memory. Its
source of truth is the worktree, the frozen brief and this controller-written
package: run/cycle identity, worktree/HEAD/snapshot, brief and config hashes,
the current diff, hashes of every validation, browser and review artifact, the
implementation status, the classified failure, the providers involved and the
rollover count. `handoff_errors` re-checks all of it immediately before takeover.
"""

import json
from pathlib import Path
from typing import Any, Optional

from autobuild.browser_contract import digest, safe_file
from autobuild.git_client import GitClient
from autobuild.git_evidence import capture
from autobuild.rollover_policy import settings, transition_error

KIND = "autobuild-rollover-handoff"


def handoff_directory(index: int) -> str:
    return f"rollover/rollover-{index:02d}"


def _hashed(run_dir: Path, relative: str) -> dict[str, str]:
    return {"path": relative, "sha256": digest(run_dir / relative)}


def build_handoff(*, run_dir: Path, state: dict[str, Any], config_data: dict[str, Any], git: GitClient,
                  index: int, failed_attempt: int, failure: dict[str, str], from_provider: str,
                  from_session: Optional[str], to_provider: Optional[str], approval: str,
                  decision: dict[str, Any], executed_before: int, created_at: str) -> tuple[str, str, Any]:
    """Write rollover/rollover-NN/handoff.json plus its Git snapshot; return (artifact, sha256, evidence)."""
    directory = handoff_directory(index)
    worktree = Path(state["worktree"])
    evidence = capture(git, worktree, run_dir, state["base_commit"], out=run_dir / directory)
    report = f"implementation/cycle-{failed_attempt:02d}/result.json"
    reviews = [{"cycle": r["cycle"], "status": r["status"], **_hashed(run_dir, r["artifact"])}
               for r in state.get("review_history", [])]
    pending = reviews[-1] if reviews and reviews[-1]["status"] == "REVISE" else None
    document = {
        "schema_version": 1, "kind": KIND, "index": index, "created_at": created_at,
        "run_id": state["run_id"], "implementation_id": state["implementation_id"], "role": "implementer",
        "review_cycle": state["review_cycle"], "failed_attempt": failed_attempt,
        "failure": failure,
        "from": {"provider": from_provider, "session_id": from_session},
        "to": {"provider": to_provider},
        "approval": approval, "decision": decision,
        "rollover_count": executed_before, "max_rollovers": settings(config_data)["max_rollovers"],
        "worktree": str(worktree), "branch": state["branch"], "base_commit": state["base_commit"],
        "head_commit": evidence.head_commit, "snapshot_tree": evidence.snapshot_tree,
        "changed_paths": evidence.changed_paths,
        "protected_refs": state["protected_refs"],
        "brief": _hashed(run_dir, "brief.md"), "config": _hashed(run_dir, "config.json"),
        "source": {name: _hashed(run_dir, f"{directory}/{name}") for name in ("git.json", "diff.patch", "changed-files.txt")},
        "implementation_status": {
            "attempts": [{key: attempt.get(key) for key in ("attempt", "cycle", "provider", "mode", "session_id")}
                         for attempt in state.get("revision_history", [])],
            "failed_attempt_report": _hashed(run_dir, report) if (run_dir / report).is_file() else None,
        },
        "evidence": {
            "validation": [{k: r[k] for k in ("attempt", "review_cycle", "artifact", "sha256", "snapshot_tree", "passed")}
                           for r in state.get("validation_history", [])],
            "browser": [{k: r[k] for k in ("attempt", "review_cycle", "artifact", "sha256", "snapshot_tree", "passed")}
                        for r in state.get("browser_history", [])],
            "reviews": reviews,
        },
        "pending_review": pending,
    }
    path = run_dir / directory / "handoff.json"
    path.write_text(json.dumps(document, indent=2) + "\n")
    return f"{directory}/handoff.json", digest(path), evidence


def handoff_errors(*, run_dir: Path, state: dict[str, Any], record: dict[str, Any], config_data: dict[str, Any],
                   git: GitClient, protected_now: dict[str, Optional[str]]) -> list[str]:
    """Everything that must still hold for a takeover from `record`; empty when it may proceed."""
    path = run_dir / record["handoff_artifact"]
    if not safe_file(path, run_dir) or digest(path) != record["handoff_sha256"]:
        return ["handoff package missing, moved or modified"]
    try:
        document = json.loads(path.read_text())
        errors = []
        if (document.get("kind"), document["run_id"], document["implementation_id"], document["index"]) != (
                KIND, state["run_id"], state["implementation_id"], record["index"]):
            errors.append("handoff identity does not match the run")
        if (document["failure"]["kind"], document["from"]["provider"], document["to"]["provider"]) != (
                record["failure"]["kind"], record["from_provider"], record["to_provider"]):
            errors.append("handoff decision does not match controller history")
        if document["brief"]["sha256"] != state["brief_sha256"]:
            errors.append("handoff brief hash does not match the frozen brief")
        hashed = [document["brief"], document["config"], *document["source"].values(),
                  *(item for item in [document["implementation_status"]["failed_attempt_report"]] if item),
                  *({"path": r["artifact"], "sha256": r["sha256"]} for r in document["evidence"]["validation"]),
                  *({"path": r["artifact"], "sha256": r["sha256"]} for r in document["evidence"]["browser"]),
                  *({"path": r["path"], "sha256": r["sha256"]} for r in document["evidence"]["reviews"])]
        for item in hashed:
            target = run_dir / item["path"]
            if not safe_file(target, run_dir) or digest(target) != item["sha256"]:
                errors.append("handoff-referenced artifact missing or modified: " + item["path"])
        worktree = Path(state["worktree"])
        if document["worktree"] != str(worktree) or document["branch"] != state["branch"]:
            errors.append("handoff worktree identity does not match the run")
        elif git.current_branch(worktree) != state["branch"] or git.read(
                "rev-parse", "HEAD", cwd=worktree).strip() != document["head_commit"]:
            errors.append("worktree branch or HEAD changed since the handoff")
        else:
            now = capture(git, worktree, run_dir, state["base_commit"], out=run_dir / record["handoff_artifact"].rsplit("/", 1)[0] / "verify")
            if now.snapshot_tree != document["snapshot_tree"]:
                errors.append("worktree source changed since the handoff")
        if not (document["protected_refs"] == state["protected_refs"] == protected_now):
            errors.append("protected refs changed since the handoff")
        executed = sum(1 for r in state.get("rollover_history", []) if r["status"] == "executed")
        if executed >= settings(config_data)["max_rollovers"]:
            errors.append("rollover budget exhausted")
        if record["to_provider"] is None:
            errors.append("handoff names no replacement implementer")
        else:
            problem = transition_error(config_data, record["failure"]["kind"], record["from_provider"], record["to_provider"])
            if problem:
                errors.append("unsupported provider transition: " + problem)
        return errors
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"handoff package is unreadable or malformed: {exc}"]


def takeover_prompt(*, base_prompt: str, handoff: dict[str, Any], run_dir: Path, review: Optional[dict]) -> str:
    """A fresh session taking over preserved work: never framed as a continued conversation."""
    diff_path = run_dir / handoff["source"]["diff.patch"]["path"]
    changed = "\n".join(f"- {path}" for path in handoff["changed_paths"][:50]) or "- (no changes yet)"
    blocks = [
        "# Take Over An Existing Implementation",
        f"You are a NEW implementer session ({handoff['to']['provider']}). You are not continuing an earlier "
        "conversation and have none of its memory or reasoning.",
        f"The previous implementer ({handoff['from']['provider']}, session {handoff['from']['session_id']}) stopped: "
        f"{handoff['failure']['kind']}: {handoff['failure']['detail']}",
        "The controller froze the run and verified this handoff package: " + str(run_dir / f"rollover/rollover-{handoff['index']:02d}/handoff.json"),
        "Source of truth, in this order: the worktree itself, the approved brief below, and the controller handoff. "
        "Do not assume the previous implementer's reasoning or report is correct; verify against the code.",
        "1. Inspect the worktree and its current diff (`git status`, `git diff`; controller copy: " + str(diff_path) + ").\n"
        "2. Read the approved brief and the handoff.\n"
        "3. Identify what is complete, partial, or missing.\n"
        "4. Preserve valid existing work and continue only what remains. Restart from scratch only if the existing "
        "state is unusable, and say so in known_issues.\n"
        "5. The controller reruns validation and browser gates on your result and starts a fresh reviewer; "
        "earlier evidence does not count for your changes.",
        "## Changes Present At Handoff\n" + changed,
    ]
    if review:
        blocks.append("## Required Review Findings (still open)\n" + json.dumps(
            {"cycle": review["cycle"], "findings": review["findings"]}, indent=2))
    blocks.append("---\n\n" + base_prompt)
    return "\n\n".join(blocks) + "\n"
