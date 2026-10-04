"""Deterministic, filesystem-safe names for run ids, branches and worktrees."""

import re
from datetime import date
from pathlib import Path
from typing import Callable

_MAX_SLUG = 40


def slugify(text: str, max_length: int = _MAX_SLUG) -> str:
    """'Instagram Derived Posts!' -> 'instagram-derived-posts'."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "change"


def safe_id(implementation_id: str) -> str:
    """Implementation id usable in branch and directory names (no '..', no trailing '.')."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", implementation_id)
    cleaned = re.sub(r"\.{2,}", ".", cleaned).strip(".-")
    return cleaned or "item"


def _first_free(base: str, taken: Callable[[str], bool]) -> str:
    if not taken(base):
        return base
    n = 2
    while taken(f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"


def run_id_for(implementation_id: str, runs_root: Path, today: date) -> str:
    """'<YYYY-MM-DD>-<id>', suffixed -2, -3 … when a run with that id already exists."""
    return _first_free(f"{today.isoformat()}-{safe_id(implementation_id)}", lambda c: (runs_root / c).exists())


def branch_name_for(prefix: str, implementation_id: str, title: str, exists: Callable[[str], bool]) -> str:
    """'<prefix><id>-<title-slug>', suffixed -2, -3 … when the branch already exists."""
    return _first_free(f"{prefix}{safe_id(implementation_id)}-{slugify(title)}", exists)


def default_worktree_root(project_root: Path) -> Path:
    """'<parent>/<project>.worktrees' — beside the project, never inside it."""
    return project_root.parent / f"{project_root.name}.worktrees"


def resolve_worktree_root(configured: str | None, project_root: Path) -> Path:
    if not configured:
        return default_worktree_root(project_root)
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()
