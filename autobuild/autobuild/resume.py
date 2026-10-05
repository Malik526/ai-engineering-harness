"""Read-only checks for explicit human resumption of a preserved run."""

import copy
import hashlib
import json
from pathlib import Path

from autobuild.autonomy import evaluate_gate
from autobuild.command_guard import is_within
from autobuild.config import load_project_config
from autobuild.front_matter import split_front_matter
from autobuild.implementations import brief_errors
from autobuild.git_client import GitClient, GitError
from autobuild.preflight import PreflightError, RunPlan, completed_from_siblings
from autobuild.provider_loader import load_adapter, ProviderLoadError
from autobuild.roles import IMPLEMENTER, REVIEWER
from autobuild.run_state_checks import run_state_errors
from autobuild.schemas import schema_errors
from autobuild.secret_files import secret_like
from autobuild.validation_runner import command_unavailable
from autobuild.browser_contract import history_errors
from autobuild.validation_contract import history_errors as validation_history_errors


def resume_preflight(run: Path, project_root: Path) -> RunPlan:
    root = project_root.resolve()
    try:
        config = load_project_config(root)
        directory = run.resolve() if run.is_dir() else (config.path("runs_directory") / run).resolve()
        if not is_within(directory, config.path("runs_directory")):
            raise ValueError("run is outside configured runs_directory")
        state = json.loads((directory / "state.json").read_text())
        errors = run_state_errors(state, config)
        if errors:
            raise ValueError("invalid run state: " + "; ".join(errors))
        if state["state"] not in ("STOPPED", "FAILED", "HUMAN_BLOCKED"):
            raise ValueError("only STOPPED, recoverable FAILED or HUMAN_BLOCKED runs can resume")
        if state["state"] == "FAILED" and not state["failure"]["recoverable"]:
            raise ValueError("failure is not recoverable")
        if state["review_mode"] != "independent" or not {"protected_refs", "review_history", "revision_history",
                                                         "validation_history", "final_review_status"} <= state.keys():
            raise ValueError("legacy runs lack the evidence needed for safe resume")
        attempts = state["revision_history"]
        if not attempts or [r["attempt"] for r in attempts] != list(range(1, len(attempts) + 1)):
            raise ValueError("implementation attempt history is missing or inconsistent")
        for attempt in attempts:
            expected = f"implementation/cycle-{attempt['attempt']:02d}"
            if attempt["artifact_directory"] != expected or not (directory / expected / "prompt.md").is_file():
                raise ValueError("implementation history artifact is missing or inconsistent")
        if (directory / ".controller.lock").exists():
            raise ValueError("controller lock exists; verify no controller is active before removing a stale lock")
        if state["review_cycle"] >= config.max_review_cycles:
            raise ValueError("review budget exhausted; human must increase max_review_cycles before resume")
        original = json.loads((directory / "config.json").read_text())
        current = copy.deepcopy(config.data)
        for document in (original, current):
            document["limits"].pop("max_review_cycles", None)
        if original != current:
            raise ValueError("execution configuration changed; only max_review_cycles may change on resume")
        frozen = directory / "brief.md"
        if hashlib.sha256(frozen.read_bytes()).hexdigest() != state.get("brief_sha256"):
            raise ValueError("frozen approved brief hash mismatch")
        meta, body = split_front_matter(frozen.read_text())
        issues = brief_errors(meta, body)
        issues.extend(history_errors(directory, state))
        issues.extend(validation_history_errors(directory, state))
        for record in state.get("browser_history", []):
            expected = f"browser/cycle-{record['attempt']:02d}/results.json"
            if record["artifact"] != expected or record["attempt"] > len(attempts):
                issues.append("browser history has an inconsistent attempt/path")
        gate = evaluate_gate(meta, completed_from_siblings(config.path("roadmap") / f"{meta['id']}.md"))
        if not gate.may_continue:
            issues.extend(gate.reasons)
        if meta["id"] != state["implementation_id"] or directory.name != state["run_id"]:
            issues.append("run/implementation identity mismatch")
        git = GitClient(root, config.protected_branches)
        if git.toplevel(root) != root:
            issues.append("project root is not a repository top level")
        worktree = Path(state["worktree"]).resolve()
        if is_within(worktree, root) or not worktree.is_dir():
            issues.append("preserved worktree is missing or inside the project")
        elif git.toplevel(worktree) != worktree:
            issues.append("preserved path is not a worktree root")
        else:
            common = git.read("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=worktree).strip()
            if common != git.read("rev-parse", "--path-format=absolute", "--git-common-dir").strip():
                issues.append("worktree belongs to a different repository")
            if git.current_branch(worktree) != state["branch"]:
                issues.append("preserved worktree branch changed")
            if git.read("rev-parse", "HEAD", cwd=worktree).strip() != (state["last_commit"] or state["base_commit"]):
                issues.append("preserved worktree HEAD changed")
            if GitClient(worktree, config.protected_branches).operation_in_progress():
                issues.append("Git operation in progress in the worktree")
            paths = git.read("diff", "--name-only", state["base_commit"], cwd=worktree).splitlines()
            paths += git.read("ls-files", "--others", "--exclude-standard", cwd=worktree).splitlines()
            if secret_like(paths):
                issues.append("secret-like files in preserved changes")
        if git.protected_refs() != state["protected_refs"]:
            issues.append("protected branch refs changed since this run started")
        if git.operation_in_progress():
            issues.append("Git operation in progress in the project")
        assignments = config.agents
        adapter = load_adapter(assignments[IMPLEMENTER])
        health = adapter.health_check()
        if not health.available:
            issues.append(f"configured implementer unavailable: {health.detail}")
        reviewer_health = load_adapter(assignments[REVIEWER]).health_check()
        if not reviewer_health.available:
            issues.append(f"configured reviewer unavailable: {reviewer_health.detail}")
        commands = list(config.data["validation"].get("commands", []))
        for command in commands:
            unavailable = command_unavailable(command, root)
            if unavailable:
                issues.append(unavailable)
        for record in state.get("review_history", []):
            artifact = directory / record["artifact"]
            if not is_within(artifact, directory) or not artifact.is_file():
                issues.append("review history artifact is missing or outside the run")
                continue
            review = json.loads(artifact.read_text())
            if schema_errors("review", review):
                issues.append("persisted review violates its schema")
            elif (review["run_id"], review["implementation_id"], review["cycle"], review["status"],
                  review["reviewer"]["session_id"]) != (state["run_id"], state["implementation_id"], record["cycle"],
                                                      record["status"], record["session_id"]):
                issues.append("persisted review does not match controller history")
            validation_artifact = directory / record["validation_artifact"]
            if not is_within(validation_artifact, directory) or not validation_artifact.is_file():
                issues.append("persisted validation artifact is missing or outside the run")
            browser_records = {item["artifact"]: item for item in state.get("browser_history", [])}
            validation_records = {item["artifact"]: item for item in state.get("validation_history", [])}
            if record.get("browser_artifact") not in (None, *browser_records):
                issues.append("review references missing browser history")
            elif record.get("browser_artifact"):
                browser_record = browser_records[record["browser_artifact"]]
                if (browser_record["review_cycle"], browser_record["snapshot_tree"]) != (
                        record["cycle"], record["snapshot_tree"]):
                    issues.append("review browser evidence does not match its cycle/source")
            if record["validation_artifact"] not in validation_records:
                issues.append("review references missing validation history")
            else:
                validation_record = validation_records[record["validation_artifact"]]
                if (validation_record["review_cycle"], validation_record["snapshot_tree"]) != (
                        record["cycle"], record["snapshot_tree"]):
                    issues.append("review validation evidence does not match its cycle/source")
        if issues:
            raise PreflightError(issues)
        return RunPlan(config=config, project_root=root, brief_path=frozen, meta=meta, body=body,
                       gate=gate, assignment=assignments[IMPLEMENTER], adapter=adapter, health=health,
                       base_branch=state["parent_branch"], base_commit=state["base_commit"], branch=state["branch"],
                       run_id=state["run_id"], run_dir=directory, worktree=worktree, validation_commands=commands,
                       implementer_timeout=config.data["limits"].get("implementer_timeout_seconds", 3600),
                       checkpoint_commits=bool(config.data["git"].get("checkpoint_commits", False)),
                       browser_gate=bool(meta["validation"]["browser_required"]),
                       reviewer_assignment=assignments[REVIEWER],
                       reviewer_timeout=config.data["limits"].get("reviewer_timeout_seconds", 3600), resume_state=state)
    except PreflightError:
        raise
    except (OSError, ValueError, KeyError, TypeError, GitError, ProviderLoadError) as exc:
        raise PreflightError([f"resume: {exc}"]) from exc
