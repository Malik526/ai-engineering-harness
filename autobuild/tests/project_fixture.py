"""Build disposable git projects configured for autobuild, for runner tests."""

import subprocess
from pathlib import Path
from typing import Any, Optional

import yaml

BRIEF = """---
id: "T-1"
title: Add feature file
status: ready
autonomy: green
depends_on: []
human_requirements: []
external_requirements: []
acceptance:
  - feature.txt exists
validation:
  tests_required: true
  browser_required: {browser}
  human_validation_required: false
approval:
  approved_by: human
  approved_at: "2026-10-04"
---

# T-1 — Add feature file

## Objective

Create feature.txt.

## Scope

- feature.txt

## Non-Goals

- Nothing else

## Acceptance Criteria

feature.txt exists.
"""

DEFAULT_COMMANDS = [{"name": "feature-exists", "kind": "test", "command": ["test", "-f", "feature.txt"]}]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def make_project(tmp_path: Path, *, provider: str = "fake-a", commands: Optional[list[dict[str, Any]]] = None,
                 checkpoint: bool = True, browser: bool = False, extra_git: Optional[dict[str, Any]] = None,
                 reviewer: Optional[str] = None, max_cycles: int = 3,
                 browser_gates: Optional[list[dict]] = None, rollover: Optional[dict] = None) -> tuple[Path, Path]:
    """Create <tmp>/proj on main with a GREEN brief; return (project root, brief path)."""
    root = tmp_path / "proj"
    (root / "docs" / "decisions").mkdir(parents=True)
    (root / "docs" / "roadmap").mkdir()
    (root / ".autobuild" / "runs").mkdir(parents=True)
    (root / "docs" / "decisions" / ".gitkeep").write_text("")
    (root / ".autobuild" / "runs" / ".gitkeep").write_text("")
    (root / "PROJECT_STATE.md").write_text("# State\n")
    (root / ".gitignore").write_text(".autobuild/runs/*\n!.autobuild/runs/.gitkeep\n")
    brief = root / "docs" / "roadmap" / "T-1.md"
    brief.write_text(BRIEF.format(browser=str(browser).lower()))
    config = {
        "version": 1,
        "project": {"name": "Fixture"},
        "agents": {"planner": {"provider": provider}, "implementer": {"provider": provider},
                   "reviewer": {"provider": reviewer or provider}},
        "git": {"protected_branches": ["main"], "branch_prefix": "agent/", "checkpoint_commits": checkpoint,
                **(extra_git or {})},
        "paths": {"roadmap": "docs/roadmap", "project_state": "PROJECT_STATE.md",
                  "adr_directory": "docs/decisions", "runs_directory": ".autobuild/runs"},
        "limits": {"max_review_cycles": max_cycles, "max_consecutive_implementations": 5, "implementer_timeout_seconds": 60},
        "validation": {"browser_tool": "none", "require_clean_git_before_start": True,
                       "commands": DEFAULT_COMMANDS if commands is None else commands},
        "notifications": {"enabled": False, "provider": "console"},
        "control": {"remote_stop_enabled": False, "provider": "none"},
    }
    if browser_gates is not None:
        config["validation"]["browser_gates"] = browser_gates
    if rollover is not None:
        config["rollover"] = rollover
    (root / ".autobuild" / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root, brief
