"""The manual-mode commit guard asks on every git commit form and stays silent otherwise.

Run: autobuild/.venv/bin/python -m pytest scripts/tests
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "git_commit_guard.py"


def _decide(command: str, tool: str = "Bash", cwd: Path | None = None) -> str:
    event = {"tool_name": tool, "tool_input": {"command": command}}
    if cwd is not None:
        event["cwd"] = str(cwd)
    done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True)
    assert done.returncode == 0
    if not done.stdout.strip():
        return "allow"
    return json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"]


@pytest.mark.parametrize("command", [
    "git commit -m x",
    "git commit --amend --no-edit",
    'git -C /repo add a && git -C /repo commit -q -m "x"',
    "cd sub; GIT_AUTHOR_NAME=a git -c user.name=b commit -am y",
    "env git --git-dir=.git --work-tree=. commit",
    "/usr/bin/git commit -m x",
    "git add . &&\ngit commit -m multi-line",
    "sudo git commit -m x",
    "env -u GIT_DIR git commit -m x",
    "command -- git commit -m x",
    "nice -n 5 git commit -m x",
    "bash -lc 'git commit -m x'",
    "git -c alias.ci=commit ci -m x",
    "git -c alias.ci=second -c alias.second=commit ci",
    "git -c 'alias.ci=!git commit' ci",
    "git -c 'alias.ci=!f() { git commit; }; f' ci",
    "alias ci='git commit'; ci -m x",
])
def test_commit_forms_ask(command):
    assert _decide(command) == "ask"


@pytest.mark.parametrize("command", [
    "git status", "git add -A", "git log --grep commit", 'echo "git commit"',
    "git diff HEAD~1", "npm test && git status --short", "git -C /repo status",
])
def test_non_commits_pass(command):
    assert _decide(command) == "allow"


def test_non_bash_tools_and_bad_input_pass():
    assert _decide("git commit -m x", tool="Read") == "allow"
    done = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout == ""


def test_repository_aliases_and_explicit_wrapper_scripts(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "alias.ci", "commit"], check=True)
    assert _decide("git ci -m x", cwd=tmp_path) == "ask"
    assert _decide(f"git -C {tmp_path} ci -m x") == "ask"
    assert _decide(f"cd {tmp_path} && git ci -m x") == "ask"
    script = tmp_path / "checkpoint.sh"
    script.write_text("#!/bin/sh\ngit ci -m x\n")
    assert _decide("./checkpoint.sh", cwd=tmp_path) == "ask"
    assert _decide("bash checkpoint.sh", cwd=tmp_path) == "ask"
    script.write_text("#!/bin/sh\ngit status\n")
    assert _decide("./checkpoint.sh", cwd=tmp_path) == "allow"
    assert _decide("echo './checkpoint.sh'", cwd=tmp_path) == "allow"
    script.write_text("#!/bin/sh\ngit commit -m x\n")
    subprocess.run(["git", "-C", str(tmp_path), "config", "alias.checkpoint", "!./checkpoint.sh"], check=True)
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    assert _decide("git checkpoint", cwd=subdir) == "ask"


def test_alias_lookup_uses_command_environment_without_executing_alias(tmp_path):
    config = tmp_path / "gitconfig"
    config.write_text("[alias]\n ci = commit\n")
    assert _decide(f"GIT_CONFIG_GLOBAL={config} git ci") == "ask"
    assert _decide("git -c alias.loop=loop loop") == "allow"
    assert _decide("git -c 'alias.probe=!touch never-created' probe", cwd=tmp_path) == "allow"
    assert not (tmp_path / "never-created").exists()
