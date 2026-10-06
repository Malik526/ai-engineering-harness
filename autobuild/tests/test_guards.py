"""Command guard, git shim, controller git client, and branch naming."""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from autobuild.git.branch_naming import branch_name_for, default_worktree_root, run_id_for, safe_id, slugify
from autobuild.git.command_guard import check_file_write, check_git, check_shell_command
from autobuild.git.git_client import GitClient, ProtectedBranchError
from autobuild.git.git_shim import write_shim
from autobuild.common.paths import CORE_ROOT
from project_fixture import git, make_project


# --- Git allowlist ---

@pytest.mark.parametrize("args", [
    ["status"], ["diff", "--stat"], ["log", "-3"], ["branch"], ["branch", "--show-current"],
    ["config", "--get", "user.name"], ["checkout", "--", "a.txt"], ["add", "-A"], ["rev-parse", "HEAD"],
    ["remote", "-v"], ["worktree", "list"], ["stash", "list"], ["symbolic-ref", "--short", "HEAD"], ["--version"],
])
def test_git_allowed(tmp_path, args):
    assert check_git(args, tmp_path, tmp_path) is None


@pytest.mark.parametrize("args", [
    ["push"], ["commit", "-m", "x"], ["merge", "main"], ["rebase", "main"], ["reset", "--hard"],
    ["checkout", "main"], ["switch", "main"], ["branch", "-D", "x"], ["branch", "new"], ["update-ref", "refs/heads/main", "x"],
    ["config", "user.name", "x"], ["worktree", "add", "x"], ["stash"], ["symbolic-ref", "HEAD", "refs/heads/main"],
    ["--git-dir=/x", "status"], ["-c", "alias.st=!rm -rf /", "st"], ["tag", "v1"], ["pull"], ["fetch"],
])
def test_git_refused(tmp_path, args):
    assert check_git(args, tmp_path, tmp_path)


def test_git_dash_c_outside_worktree_refused(tmp_path):
    (tmp_path / "wt").mkdir()
    assert check_git(["-C", "..", "status"], tmp_path / "wt", tmp_path / "wt")
    assert check_git(["-C", "sub", "status"], tmp_path / "wt", tmp_path / "wt") is None


def test_shell_scan_finds_git_in_compound_commands(tmp_path):
    assert check_shell_command("npm test && git commit -am x", tmp_path)
    assert check_shell_command("echo hi | sudo git push", tmp_path)
    assert check_shell_command("ls; git log --oneline", tmp_path) is None
    assert check_shell_command("echo 'git push is a phrase'", tmp_path) is None


def test_file_write_confined_to_worktree(tmp_path):
    assert check_file_write(str(tmp_path / "a/b.txt"), tmp_path) is None
    assert check_file_write("rel/path.txt", tmp_path) is None
    assert check_file_write("/tmp/elsewhere.txt", tmp_path / "x")
    assert check_file_write("../escape.txt", tmp_path)


def test_git_shim_refuses_and_passes_through(tmp_path):
    shim = write_shim(tmp_path / "bin", sys.executable, CORE_ROOT)
    env = {**os.environ, "AUTOBUILD_REAL_GIT": "/usr/bin/git" if Path("/usr/bin/git").exists() else "git",
           "AUTOBUILD_WORKTREE": str(tmp_path)}
    refused = subprocess.run([str(shim), "push"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert refused.returncode == 126 and "not allowed" in refused.stderr
    allowed = subprocess.run([str(shim), "--version"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert allowed.returncode == 0 and "git version" in allowed.stdout


# --- Controller git client ---

def test_git_client_refuses_protected_branch_writes(tmp_path):
    root, _ = make_project(tmp_path)
    client = GitClient(root, ["main"])
    head = client.commit_of("main")
    with pytest.raises(ProtectedBranchError):
        client.add_worktree(tmp_path / "wt", "main", head)
    with pytest.raises(ProtectedBranchError):
        client.commit_tree_to_branch(root, "refs/heads/main", "deadbeef", head, "x")
    assert client.commit_of("main") == head


def test_worktree_creation(tmp_path):
    root, _ = make_project(tmp_path)
    client = GitClient(root, ["main"])
    head = client.commit_of("main")
    client.add_worktree(tmp_path / "wt", "agent/x", head)
    assert client.current_branch(tmp_path / "wt") == "agent/x"
    assert git(tmp_path / "wt", "rev-parse", "HEAD").strip() == head


# --- Naming ---

def test_slug_and_ids_are_filesystem_and_ref_safe():
    assert slugify("Instagram Derived Posts!") == "instagram-derived-posts"
    assert slugify("x" * 80) == "x" * 40 and slugify("!!!") == "change"
    assert safe_id("M4.2") == "M4.2" and safe_id("a..b/c") == "a.b-c" and safe_id("..") == "item"


def test_branch_and_run_id_deterministic_with_collisions(tmp_path):
    taken = {"agent/M4.2-instagram-posts", "agent/M4.2-instagram-posts-2"}
    assert branch_name_for("agent/", "M4.2", "Instagram posts", lambda b: False) == "agent/M4.2-instagram-posts"
    assert branch_name_for("agent/", "M4.2", "Instagram posts", taken.__contains__) == "agent/M4.2-instagram-posts-3"
    (tmp_path / "2026-10-04-M4.2").mkdir()
    assert run_id_for("M4.2", tmp_path, date(2026, 10, 4)) == "2026-10-04-M4.2-2"
    assert default_worktree_root(Path("/home/u/proj")) == Path("/home/u/proj.worktrees")


def test_generated_branch_names_pass_git_check_ref_format(tmp_path):
    root, _ = make_project(tmp_path)
    client = GitClient(root, ["main"])
    for item_id, title in [("M4.2", "Posts"), ("v1..2", "weird: title?*"), ("x.lock", "end")]:
        assert client.valid_branch_name(branch_name_for("agent/", item_id, title, lambda b: False))
