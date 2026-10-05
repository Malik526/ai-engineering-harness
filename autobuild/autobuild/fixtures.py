"""Disposable live-verification fixtures: create, list, and safely clean.

Every fixture lives directly under one ignored runtime directory
(`<core>/.test-runtime`, or $AUTOBUILD_TEST_RUNTIME) with its worktrees in the
sibling `<name>.worktrees`. Ownership is recorded in `<fixture>/.git/` (never
tracked), and cleanup deletes nothing unless ownership, purpose, location and
every worktree check out.

Fixtures created before this module existed (bare `~/autobuild-fixture-*`
folders) can be cleaned only through the stricter legacy check.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Optional

from autobuild import __version__
from autobuild.paths import CORE_ROOT, TEMPLATE_DIR
from autobuild.yaml_loader import load_yaml

MARKER = "autobuild-fixture.json"
OWNER = "autobuild"
PURPOSE = "live-verification-fixture"
_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_FIXTURE_TEMPLATES = TEMPLATE_DIR / "fixture"
_IDENTITY = ("-c", "user.name=Autobuild Fixture", "-c", "user.email=fixture@autobuild.invalid")
LEGACY_PROJECT_NAME = "Autobuild Fixture"


class FixtureError(ValueError):
    """A fixture cannot be created as requested."""


@dataclass
class CleanTarget:
    path: Path
    worktrees_dir: Path
    worktrees: list[Path] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.problems


def runtime_root() -> Path:
    """The single ignored directory holding every fixture."""
    configured = os.environ.get("AUTOBUILD_TEST_RUNTIME")
    return Path(configured).expanduser().resolve() if configured else CORE_ROOT / ".test-runtime"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


# --- Create ---

def create_fixture(*, implementer: str, name: Optional[str] = None, root: Optional[Path] = None,
                   browser: bool = False) -> Path:
    """Create a fixture repository on `main` with the standard V-1 brief; return its path."""
    root = (root or runtime_root()).resolve()
    if name is None:
        base = f"live-{datetime.now().strftime('%Y%m%d')}-{implementer}"
        name, n = base, 2
        while (root / name).exists() or (root / f"{name}.worktrees").exists():
            name, n = f"{base}-{n}", n + 1
    if not _NAME.match(name) or name.endswith(".worktrees"):
        raise FixtureError(f"invalid fixture name {name!r}")
    path = root / name
    if path.exists() or (root / f"{name}.worktrees").exists():
        raise FixtureError(f"{path} already exists")

    for sub in ("docs/decisions", "docs/roadmap", ".autobuild/runs"):
        (path / sub).mkdir(parents=True)
    (path / "docs/decisions/.gitkeep").write_text("")
    (path / ".autobuild/runs/.gitkeep").write_text("")
    (path / "PROJECT_STATE.md").write_text("# Fixture State\n")
    (path / ".gitignore").write_text(".autobuild/runs/*\n!.autobuild/runs/.gitkeep\n")
    for template in ("README.md", "AGENTS.md"):
        shutil.copyfile(_FIXTURE_TEMPLATES / template, path / template)
    shutil.copyfile(_FIXTURE_TEMPLATES / "V-1.md", path / "docs/roadmap/V-1.md")
    config = Template((_FIXTURE_TEMPLATES / "config.yaml").read_text()).substitute(implementer=implementer)
    (path / ".autobuild/config.yaml").write_text(config)
    if browser:
        import yaml
        source = TEMPLATE_DIR / "browser-fixture"
        for filename in ("AGENTS.md", "package.json", "package-lock.json", "smoke.cjs", ".gitignore"):
            shutil.copyfile(source / filename, path / filename)
        shutil.copyfile(source / "V-1.md", path / "docs/roadmap/V-1.md")
        document = load_yaml(config)
        document["validation"].update(browser_tool="playwright", commands=[
            {"name": "dependencies", "kind": "setup", "run": "npm ci --ignore-scripts --offline --no-audit --no-fund"},
            {"name": "html-exists", "kind": "test", "run": "test -f index.html"}], browser_gates=[
            {"id": "counter", "kind": "e2e", "command": ["node", "smoke.cjs"], "timeout_seconds": 60,
             "required": True, "artifacts": ["counter.png", "trace.zip", "report.json"],
             "service": {"command": ["python3", "-m", "http.server", "38404", "--bind", "127.0.0.1"],
                         "ready_url": "http://127.0.0.1:38404", "timeout_seconds": 10}}])
        (path / ".autobuild/config.yaml").write_text(yaml.safe_dump(document, sort_keys=False))

    for args in (("init", "-q", "-b", "main"), ("add", "-A"), (*_IDENTITY, "commit", "-q", "-m", "fixture")):
        done = _git(path, *args)
        if done.returncode != 0:
            raise FixtureError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    marker = {
        "owner": OWNER, "purpose": PURPOSE, "name": name, "path": str(path),
        "implementer": implementer, "autobuild_version": __version__,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (path / ".git" / MARKER).write_text(json.dumps(marker, indent=2) + "\n")
    return path


# --- Inspect ---

def _registered_worktrees(repo: Path) -> tuple[list[Path], Optional[str]]:
    """Linked worktree paths registered in `repo` (excluding the main checkout)."""
    done = _git(repo, "worktree", "list", "--porcelain")
    if done.returncode != 0:
        return [], f"cannot list worktrees: {done.stderr.strip()}"
    paths = [Path(line[len("worktree "):]) for line in done.stdout.splitlines() if line.startswith("worktree ")]
    return [p for p in paths if p.resolve() != repo.resolve()], None


def _check_location_and_worktrees(target: CleanTarget) -> None:
    path, worktrees_dir = target.path, target.worktrees_dir
    if path.is_symlink() or not path.is_dir():
        target.problems.append("not a real directory (missing or a symlink)")
        return
    if not (path / ".git").is_dir():
        target.problems.append("no .git directory (not a standalone fixture repository)")
        return
    worktrees, error = _registered_worktrees(path)
    if error:
        target.problems.append(error)
    for worktree in worktrees:
        if worktree.resolve().parent != worktrees_dir.resolve():
            target.problems.append(f"registered worktree {worktree} is outside {worktrees_dir}")
    target.worktrees = worktrees
    if worktrees_dir.exists() or worktrees_dir.is_symlink():
        if worktrees_dir.is_symlink() or not worktrees_dir.is_dir():
            target.problems.append(f"{worktrees_dir} is not a real directory")
        else:
            known = {w.resolve() for w in worktrees}
            unknown = [e.name for e in worktrees_dir.iterdir() if e.resolve() not in known or e.is_symlink()]
            if unknown:
                target.problems.append(f"{worktrees_dir} holds entries that are not this fixture's worktrees: {', '.join(sorted(unknown))}")
    for worktree in worktrees:
        if worktree.is_symlink():
            target.problems.append(f"worktree {worktree} is a symlink")


def inspect_fixture(name: str, root: Optional[Path] = None) -> CleanTarget:
    """Verify ownership, purpose and location of the fixture `name` under the runtime root."""
    root = (root or runtime_root()).resolve()
    path = root / name
    target = CleanTarget(path=path, worktrees_dir=root / f"{name}.worktrees")
    if not _NAME.match(name) or name.endswith(".worktrees"):
        target.problems.append("not a fixture name")
        return target
    _check_location_and_worktrees(target)
    if target.problems:
        return target
    try:
        marker = json.loads((path / ".git" / MARKER).read_text())
    except (OSError, json.JSONDecodeError):
        target.problems.append("no readable ownership marker (.git/autobuild-fixture.json)")
        return target
    if marker.get("owner") != OWNER or marker.get("purpose") != PURPOSE:
        target.problems.append("ownership marker does not identify an autobuild live-verification fixture")
    if marker.get("name") != name or marker.get("path") != str(path):
        target.problems.append(f"ownership marker was written for {marker.get('path')}, not this location")
    return target


def inspect_legacy(path: Path) -> CleanTarget:
    """Strict check for pre-runtime fixtures (no marker): every signature must match."""
    path = Path(os.path.abspath(path.expanduser()))
    target = CleanTarget(path=path, worktrees_dir=path.parent / f"{path.name}.worktrees")
    if not path.name.startswith("autobuild-fixture"):
        target.problems.append("legacy fixture names start with 'autobuild-fixture'")
        return target
    _check_location_and_worktrees(target)
    if target.problems:
        return target
    try:
        config = load_yaml((path / ".autobuild/config.yaml").read_text())
        project_name = config["project"]["name"]
    except (OSError, KeyError, TypeError):
        project_name = None
    if project_name != LEGACY_PROJECT_NAME:
        target.problems.append(f"project name is {project_name!r}, not {LEGACY_PROJECT_NAME!r}")
    if not (path / "docs/roadmap/V-1.md").is_file():
        target.problems.append("missing the fixture brief docs/roadmap/V-1.md")
    roots = _git(path, "rev-list", "--max-parents=0", "--format=%s", "HEAD").stdout.splitlines()
    if [line for line in roots if not line.startswith("commit ")] != ["fixture"]:
        target.problems.append("root commit is not the single 'fixture' commit")
    if _git(path, "remote").stdout.strip():
        target.problems.append("has a git remote (fixtures never do)")
    return target


def list_fixtures(root: Optional[Path] = None) -> list[CleanTarget]:
    """Every fixture-like directory under the runtime root, with its verification result."""
    root = (root or runtime_root()).resolve()
    if not root.is_dir():
        return []
    return [inspect_fixture(entry.name, root) for entry in sorted(root.iterdir())
            if not entry.name.endswith(".worktrees")]


# --- Clean ---

def remove(target: CleanTarget) -> None:
    """Delete a verified fixture: its worktrees, the worktrees directory, then the repository."""
    if not target.safe:
        raise FixtureError(f"refusing to remove unverified {target.path}: {'; '.join(target.problems)}")
    for worktree in target.worktrees:
        if worktree.exists():
            shutil.rmtree(worktree)
    if target.worktrees_dir.is_dir():
        shutil.rmtree(target.worktrees_dir)
    shutil.rmtree(target.path)
