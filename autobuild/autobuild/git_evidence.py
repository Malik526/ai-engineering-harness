"""Capture what actually changed in a run worktree, independently of the agent's report.

The snapshot is taken through a temporary index, so the worktree's own index
is not touched, and its tree id is kept: the checkpoint commit is built from
exactly this snapshot, so files produced later by validation are never
committed by accident.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from autobuild.git_client import GitClient


@dataclass(frozen=True)
class GitEvidence:
    branch: str | None
    base_commit: str
    head_commit: str
    snapshot_tree: str
    base_tree: str
    status_porcelain: str
    untracked: tuple[str, ...]
    changed: tuple[tuple[str, str], ...]  # (status letter(s), path)

    @property
    def changed_paths(self) -> list[str]:
        return [path for _, path in self.changed]

    @property
    def has_changes(self) -> bool:
        return self.snapshot_tree != self.base_tree

    @property
    def committed_by_agent(self) -> bool:
        return self.head_commit != self.base_commit


def capture(git: GitClient, worktree: Path, run_dir: Path, base_commit: str) -> GitEvidence:
    """Snapshot the worktree and write implementation/{git.json,changed-files.txt,diff.patch}."""
    out = run_dir / "implementation"
    out.mkdir(parents=True, exist_ok=True)
    index_file = out / ".snapshot-index"
    env = {"GIT_INDEX_FILE": str(index_file)}
    try:
        git.read("read-tree", "HEAD", cwd=worktree, env=env)
        git.read("add", "--all", cwd=worktree, env=env)
        snapshot_tree = git.read("write-tree", cwd=worktree, env=env).strip()
        diff = git.read("diff", "--cached", "--binary", base_commit, cwd=worktree, env=env)
        name_status = git.read("diff", "--cached", "--name-status", base_commit, cwd=worktree, env=env)
    finally:
        index_file.unlink(missing_ok=True)

    changed = tuple(
        (fields[0], fields[-1]) for fields in (line.split("\t") for line in name_status.splitlines()) if len(fields) >= 2
    )
    evidence = GitEvidence(
        branch=git.current_branch(worktree),
        base_commit=base_commit,
        head_commit=git.read("rev-parse", "HEAD", cwd=worktree).strip(),
        snapshot_tree=snapshot_tree,
        base_tree=git.read("rev-parse", f"{base_commit}^{{tree}}", cwd=worktree).strip(),
        status_porcelain=git.read("status", "--porcelain=v1", "--untracked-files=all", cwd=worktree),
        untracked=tuple(git.read("ls-files", "--others", "--exclude-standard", cwd=worktree).splitlines()),
        changed=changed,
    )
    (out / "diff.patch").write_text(diff)
    (out / "changed-files.txt").write_text(name_status)
    record = asdict(evidence)
    record["changed"] = [{"status": s, "path": p} for s, p in evidence.changed]
    (out / "git.json").write_text(json.dumps(record, indent=2) + "\n")
    return evidence


def post_validation_status(git: GitClient, worktree: Path) -> str:
    """Worktree status after validation, to expose files the validation itself changed."""
    return git.read("status", "--porcelain=v1", "--untracked-files=all", cwd=worktree)
