"""The controller's own git access.

Reads go through `read`. Every operation that writes a ref goes through a
named method that first refuses protected branches, so no controller code
path can modify a protected branch even by mistake.
"""

import os
import subprocess
from pathlib import Path
from typing import Mapping, Optional, Sequence

from autobuild.safety import is_protected_branch


class GitError(RuntimeError):
    """A git command failed."""


class ProtectedBranchError(RuntimeError):
    """A write to a protected branch was attempted."""


class GitClient:
    def __init__(self, repo: Path, protected_branches: Sequence[str]):
        self.repo = repo
        self.protected = tuple(protected_branches)

    # --- Reads ---

    def read(self, *args: str, cwd: Optional[Path] = None, env: Optional[Mapping[str, str]] = None,
             check: bool = True) -> str:
        done = subprocess.run(["git", *args], cwd=cwd or self.repo, capture_output=True, text=True,
                              env={**os.environ, **(env or {})}, stdin=subprocess.DEVNULL)
        if check and done.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed ({done.returncode}): {done.stderr.strip()}")
        return done.stdout

    def toplevel(self, path: Path) -> Optional[Path]:
        done = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path, capture_output=True, text=True)
        return Path(done.stdout.strip()).resolve() if done.returncode == 0 else None

    def commit_of(self, ref: str) -> Optional[str]:
        done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
                              cwd=self.repo, capture_output=True, text=True)
        return done.stdout.strip() if done.returncode == 0 else None

    def branch_exists(self, name: str) -> bool:
        return self.commit_of(f"refs/heads/{name}") is not None

    def valid_branch_name(self, name: str) -> bool:
        return subprocess.run(["git", "check-ref-format", "--branch", name], cwd=self.repo,
                              capture_output=True).returncode == 0

    def protected_refs(self) -> dict[str, Optional[str]]:
        """Current commit of every protected branch (None when it does not exist locally)."""
        return {name: self.commit_of(f"refs/heads/{name}") for name in self.protected}

    def current_branch(self, worktree: Path) -> Optional[str]:
        done = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=worktree,
                              capture_output=True, text=True)
        return done.stdout.strip() if done.returncode == 0 else None

    def operation_in_progress(self) -> Optional[str]:
        """Name of an unfinished merge/rebase/cherry-pick in the main checkout, if any."""
        git_dir = Path(self.read("rev-parse", "--absolute-git-dir").strip())
        for marker, label in (("MERGE_HEAD", "merge"), ("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
                              ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert")):
            if (git_dir / marker).exists():
                return label
        return None

    # --- Guarded writes ---

    def _assert_not_protected(self, branch: str) -> None:
        if is_protected_branch(branch, self.protected):
            raise ProtectedBranchError(f"refusing to modify protected branch {branch!r}")

    def add_worktree(self, path: Path, branch: str, base_commit: str) -> None:
        """Create `branch` at `base_commit` and check it out in a new worktree at `path`."""
        self._assert_not_protected(branch)
        self.read("worktree", "add", "-b", branch, str(path), base_commit)

    def commit_tree_to_branch(self, worktree: Path, branch: str, tree: str, parent: str, message: str) -> str:
        """Commit `tree` on top of `parent` and move `branch` to it (only if it still points at `parent`)."""
        self._assert_not_protected(branch)
        commit = self.read("commit-tree", tree, "-p", parent, "-m", message, cwd=worktree).strip()
        self.read("update-ref", f"refs/heads/{branch}", commit, parent, cwd=worktree)
        # Refresh the worktree index to the new HEAD; files on disk are untouched.
        self.read("reset", "--quiet", "--mixed", cwd=worktree)
        return commit
