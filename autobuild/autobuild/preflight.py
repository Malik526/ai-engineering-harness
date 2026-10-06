"""Everything checked before a run creates any branch, worktree or run directory.

`preflight` either returns a complete RunPlan or raises PreflightError listing
every problem found. It only reads: a failed preflight leaves the repository
exactly as it was.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from autobuild.agent_provider import AgentProvider, ProviderHealth
from autobuild.autonomy import GateDecision, evaluate_gate
from autobuild.branch_naming import branch_name_for, resolve_worktree_root, run_id_for
from autobuild.command_guard import is_within
from autobuild.config import ConfigError, ProjectConfig, load_project_config
from autobuild.front_matter import FrontMatterError, split_front_matter
from autobuild.git_client import GitClient
from autobuild.implementations import brief_errors
from autobuild.provider_loader import ProviderLoadError, load_adapter
from autobuild.provider_registry import RoleAssignment, assignment_for
from autobuild.rollover_policy import settings as rollover_settings
from autobuild.roles import IMPLEMENTER, REVIEWER
from autobuild.safety import is_protected_branch
from autobuild.validation_runner import command_unavailable

DEFAULT_IMPLEMENTER_TIMEOUT = 3600


class PreflightError(Exception):
    def __init__(self, issues: list[str]):
        super().__init__("\n".join(issues))
        self.issues = issues


@dataclass
class RunPlan:
    config: ProjectConfig
    project_root: Path
    brief_path: Path
    meta: dict[str, Any]
    body: str
    gate: GateDecision
    assignment: RoleAssignment
    adapter: AgentProvider
    health: ProviderHealth
    base_branch: str
    base_commit: str
    branch: str
    run_id: str
    run_dir: Path
    worktree: Path
    validation_commands: list[dict[str, Any]]
    implementer_timeout: int
    checkpoint_commits: bool
    browser_gate: bool
    warnings: list[str] = field(default_factory=list)
    reviewer_assignment: Optional[RoleAssignment] = None
    reviewer_timeout: int = DEFAULT_IMPLEMENTER_TIMEOUT
    resume_state: Optional[dict[str, Any]] = None
    resume_rollover: Optional[dict[str, Any]] = None  # {"action": "execute"|"redecide", "record": rollover record}


def completed_from_siblings(brief_path: Path) -> set[str]:
    """Ids of briefs next to `brief_path` whose status is done (the roadmap's record of completion)."""
    done = set()
    for other in brief_path.parent.glob("*.md"):
        if other.resolve() == brief_path.resolve():
            continue
        try:
            meta, _ = split_front_matter(other.read_text())
        except (FrontMatterError, OSError):
            continue
        if meta.get("status") == "done" and isinstance(meta.get("id"), str):
            done.add(meta["id"])
    return done


def preflight(brief_path: Path, project_root: Path, *, base_branch: Optional[str] = None,
              today: Optional[date] = None) -> RunPlan:
    """Validate everything needed to start one implementation run."""
    project_root = project_root.resolve()
    brief_path = brief_path.resolve()

    # 1. Project configuration
    try:
        config = load_project_config(project_root)
    except ConfigError as exc:
        raise PreflightError([f"config: {e}" for e in exc.errors]) from exc

    # 2. Brief
    try:
        meta, body = split_front_matter(brief_path.read_text())
    except (FrontMatterError, OSError) as exc:
        raise PreflightError([f"brief: {exc}"]) from exc
    errors = brief_errors(meta, body)
    if errors:
        raise PreflightError([f"brief: {e}" for e in errors])

    issues: list[str] = []
    warnings: list[str] = []

    # 3. Autonomy
    gate = evaluate_gate(meta, completed_from_siblings(brief_path))
    if not gate.may_continue:
        issues += [f"autonomy: {r}" for r in gate.reasons]

    # 4. Configured implementer — never substituted by another provider
    assignment = config.agents[IMPLEMENTER]
    try:
        adapter = load_adapter(assignment)
        health = adapter.health_check()
    except ProviderLoadError as exc:
        raise PreflightError(issues + [f"Configured implementer: {assignment.provider}", f"Status: unavailable ({exc})"]) from exc
    if not health.available:
        issues += [f"Configured implementer: {assignment.provider}", f"Status: unavailable ({health.detail})"]

    reviewer_assignment = config.agents[REVIEWER]
    try:
        reviewer_health = load_adapter(reviewer_assignment).health_check()
        if not reviewer_health.available:
            issues += [f"Configured reviewer: {reviewer_assignment.provider}", f"Status: unavailable ({reviewer_health.detail})"]
    except ProviderLoadError as exc:
        issues += [f"Configured reviewer: {reviewer_assignment.provider}", f"Status: unavailable ({exc})"]

    # Rollover replacements are checked again at takeover; an unhealthy one now is only a warning.
    for candidate in rollover_settings(config.data)["implementer"]:
        try:
            candidate_health = load_adapter(assignment_for(config.data, IMPLEMENTER, candidate)).health_check()
            available, detail = candidate_health.available, candidate_health.detail
        except ProviderLoadError as exc:
            available, detail = False, str(exc)
        if not available:
            warnings.append(f"rollover implementer {candidate} is unavailable now ({detail}); a rollover to it would block")

    # 5. Git repository
    git = GitClient(project_root, config.protected_branches)
    if git.toplevel(project_root) != project_root:
        raise PreflightError(issues + [f"git: {project_root} is not the top level of a git repository"])
    in_progress = git.operation_in_progress()
    if in_progress:
        issues.append(f"git: a {in_progress} is in progress in {project_root}")
    if config.data["validation"]["require_clean_git_before_start"]:
        dirty = git.read("status", "--porcelain").splitlines()
        if dirty:
            issues.append(f"git: working tree has {len(dirty)} uncommitted change(s) and require_clean_git_before_start is true")

    # 6. Protected-branch policy
    base = base_branch or config.data["git"].get("default_base_branch") or config.protected_branches[0]
    base_commit = git.commit_of(f"refs/heads/{base}")
    if base_commit is None:
        issues.append(f"git: base branch {base!r} does not exist locally")
    elif not (is_protected_branch(base, config.protected_branches) or base.startswith(config.branch_prefix)):
        issues.append(f"git: base branch {base!r} is neither a protected branch nor an automation branch ({config.branch_prefix}*)")
    branch = branch_name_for(config.branch_prefix, meta["id"], meta["title"], git.branch_exists)
    if is_protected_branch(branch, config.protected_branches) or not git.valid_branch_name(branch):
        issues.append(f"git: cannot use {branch!r} as a run branch")

    # 7. Required paths
    for key in ("project_state", "adr_directory"):
        if not config.path(key).exists():
            issues.append(f"paths.{key}: {config.path(key)} does not exist")
    if not config.path("roadmap").exists():
        warnings.append(f"paths.roadmap: {config.path('roadmap')} does not exist")
    runs_root = config.path("runs_directory")
    run_id = run_id_for(meta["id"], runs_root, today or date.today())
    worktree_root = resolve_worktree_root(config.data["git"].get("worktree_root"), project_root)
    worktree = worktree_root / run_id

    # 8. Conflicts
    if is_within(worktree_root, project_root):
        issues.append(f"git.worktree_root: {worktree_root} is inside the project; worktrees must live outside it")
    if worktree.exists():
        issues.append(f"worktree: {worktree} already exists")

    # 9. Validation commands
    commands = list(config.data["validation"].get("commands", []))
    for spec in commands:
        reason = command_unavailable(spec, project_root)
        if reason:
            issues.append(reason)
    for relative in config.data["validation"].get("runtime_paths", []):
        runtime_path = project_root / relative
        if runtime_path.is_symlink() or not runtime_path.exists() or not is_within(runtime_path, project_root):
            issues.append(f"validation.runtime_paths: {relative} is missing, linked or outside the project")
    if meta["validation"]["tests_required"] and not any(c["kind"] == "test" for c in commands):
        issues.append("validation: the brief requires tests but the project config defines no `test` command")
    browser_gate = bool(meta["validation"]["browser_required"])
    if browser_gate and not any(g.get("required", True) and g.get("enabled", True)
                                for g in config.data["validation"].get("browser_gates", [])):
        warnings.append("brief requires browser validation but no enabled required browser gate is configured; "
                        "checkpointing is blocked until coverage is configured in a new run")

    if issues:
        raise PreflightError(issues)
    return RunPlan(
        config=config, project_root=project_root, brief_path=brief_path, meta=meta, body=body, gate=gate,
        assignment=assignment, adapter=adapter, health=health, base_branch=base, base_commit=base_commit or "",
        branch=branch, run_id=run_id, run_dir=runs_root / run_id, worktree=worktree,
        validation_commands=commands,
        implementer_timeout=config.data["limits"].get("implementer_timeout_seconds", DEFAULT_IMPLEMENTER_TIMEOUT),
        checkpoint_commits=bool(config.data["git"].get("checkpoint_commits", False)),
        browser_gate=browser_gate, warnings=warnings,
        reviewer_assignment=reviewer_assignment,
        reviewer_timeout=config.data["limits"].get("reviewer_timeout_seconds", DEFAULT_IMPLEMENTER_TIMEOUT),
    )
