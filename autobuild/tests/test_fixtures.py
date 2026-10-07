"""Fixture lifecycle and the cleanup ownership checks."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from autobuild import fixtures
from autobuild.core.config import load_project_config
from autobuild.git.git_client import GitClient


@pytest.fixture
def root(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("AUTOBUILD_TEST_RUNTIME", str(runtime))
    return runtime


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _with_worktree(path: Path) -> Path:
    client = GitClient(path, ["main"])
    worktree = path.parent / f"{path.name}.worktrees" / "run-1"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    client.add_worktree(worktree, "agent/V-1-x", client.commit_of("main"))
    return worktree


def test_create_makes_a_clean_marked_valid_fixture(root):
    path = fixtures.create_fixture(implementer="claude")
    assert path.parent == root.resolve() and path.name.startswith("live-") and path.name.endswith("-claude")
    marker = json.loads((path / ".git" / fixtures.MARKER).read_text())
    assert marker["owner"] == "autobuild" and marker["purpose"] == fixtures.PURPOSE and marker["path"] == str(path)
    assert _git(path, "status", "--porcelain") == ""  # marker lives in .git, never dirties the tree
    config = load_project_config(path)
    assert config.agents["implementer"].provider == "claude" and config.name == "Autobuild Fixture"
    assert (path / "docs/roadmap/README.md").exists()
    assert (path / "docs/roadmap/verification/V-1.md").exists()
    second = fixtures.create_fixture(implementer="claude")
    assert second.name == f"{path.name}-2"


def test_create_rejects_bad_or_taken_names(root):
    with pytest.raises(fixtures.FixtureError):
        fixtures.create_fixture(implementer="claude", name="../escape")
    fixtures.create_fixture(implementer="claude", name="f1")
    with pytest.raises(fixtures.FixtureError):
        fixtures.create_fixture(implementer="claude", name="f1")


def test_browser_fixture_is_clean_and_explicit(root):
    path = fixtures.create_fixture(implementer="codex", name="browser", browser=True)
    config = load_project_config(path)
    assert config.data["validation"]["browser_gates"][0]["command"] == ["node", "smoke.cjs"]
    assert (path / "package-lock.json").is_file()
    assert "browser_required: true" in (path / "docs/roadmap/verification/V-1.md").read_text()
    assert _git(path, "status", "--porcelain") == ""


def test_clean_removes_verified_fixture_and_worktrees(root):
    path = fixtures.create_fixture(implementer="codex", name="f1")
    worktree = _with_worktree(path)
    target = fixtures.inspect_fixture("f1")
    assert target.safe and target.worktrees == [worktree]
    fixtures.remove(target)
    assert not path.exists() and not worktree.parent.exists()
    assert list(root.iterdir()) == []


def test_list_reports_owned_and_unverified(root):
    fixtures.create_fixture(implementer="claude", name="good")
    (root / "stray").mkdir()
    results = {t.path.name: t for t in fixtures.list_fixtures()}
    assert results["good"].safe and not results["stray"].safe


def test_refuses_unmarked_repository(root):
    path = root / "plain"
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    target = fixtures.inspect_fixture("plain")
    assert not target.safe and any("marker" in p for p in target.problems)
    with pytest.raises(fixtures.FixtureError):
        fixtures.remove(target)
    assert path.exists()


def test_refuses_symlink_and_copied_marker(root, tmp_path):
    real = fixtures.create_fixture(implementer="claude", name="real")
    (root / "link").symlink_to(real)
    assert not fixtures.inspect_fixture("link").safe
    copy = root / "copy"
    subprocess.run(["cp", "-r", str(real), str(copy)], check=True)
    target = fixtures.inspect_fixture("copy")
    assert not target.safe and any("written for" in p for p in target.problems)


def test_refuses_worktree_outside_runtime_and_unknown_worktree_entries(root, tmp_path):
    path = fixtures.create_fixture(implementer="claude", name="f1")
    client = GitClient(path, ["main"])
    client.add_worktree(tmp_path / "elsewhere", "agent/out", client.commit_of("main"))
    target = fixtures.inspect_fixture("f1")
    assert not target.safe and any("outside" in p for p in target.problems)

    other = fixtures.create_fixture(implementer="claude", name="f2")
    (root / "f2.worktrees").mkdir()
    (root / "f2.worktrees" / "someone-elses-work").mkdir()
    target = fixtures.inspect_fixture("f2")
    assert not target.safe and any("not this fixture's worktrees" in p for p in target.problems)
    assert other.exists()


def test_refuses_names_that_are_not_fixtures(root):
    root.mkdir(parents=True)
    assert not fixtures.inspect_fixture("../x").safe
    assert not fixtures.inspect_fixture("f1.worktrees").safe
    assert not fixtures.inspect_fixture("missing").safe


# --- Legacy (pre-runtime) fixtures ---

def _legacy(tmp_path: Path, name: str = "autobuild-fixture-0.2") -> Path:
    path = fixtures.create_fixture(implementer="claude", name=f"seed-{name}", root=tmp_path / "seedroot")
    legacy = tmp_path / "home" / name
    legacy.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-r", str(path), str(legacy)], check=True)
    nested_brief = legacy / "docs/roadmap/verification/V-1.md"
    nested_brief.replace(legacy / "docs/roadmap/V-1.md")
    nested_brief.parent.rmdir()
    (legacy / "docs/roadmap/README.md").unlink()
    (legacy / ".git" / fixtures.MARKER).unlink()  # legacy fixtures had no marker
    return legacy


def test_legacy_fixture_with_matching_signature_is_removable(tmp_path):
    legacy = _legacy(tmp_path)
    worktree = _with_worktree(legacy)
    target = fixtures.inspect_legacy(legacy)
    assert target.safe, target.problems
    fixtures.remove(target)
    assert not legacy.exists() and not worktree.exists()


def test_legacy_refusals(tmp_path):
    assert not fixtures.inspect_legacy(tmp_path / "my-project").safe  # wrong name
    with_remote = _legacy(tmp_path, "autobuild-fixture-remote")
    _git(with_remote, "remote", "add", "origin", "https://example.invalid/x.git")
    assert any("remote" in p for p in fixtures.inspect_legacy(with_remote).problems)
    renamed = _legacy(tmp_path, "autobuild-fixture-renamed")
    config = renamed / ".autobuild/config.yaml"
    config.write_text(config.read_text().replace("Autobuild Fixture", "Real Project"))
    assert any("project name" in p for p in fixtures.inspect_legacy(renamed).problems)


def test_cli_clean_is_dry_run_by_default(root, capsys):
    from autobuild.cli import main

    fixtures.create_fixture(implementer="claude", name="f1")
    assert main(["fixture", "clean", "f1"]) == 0
    assert "WOULD REMOVE" in capsys.readouterr().out and (root / "f1").exists()
    assert main(["fixture", "clean", "f1", "--yes"]) == 0
    assert not (root / "f1").exists()
    assert main(["fixture", "clean", "nope"]) == 1
