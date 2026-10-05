"""The manual-mode commit guard asks on every git commit form and stays silent otherwise.

Run: autobuild/.venv/bin/python -m pytest scripts/tests
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "git_commit_guard.py"


def _decide(command: str, tool: str = "Bash") -> str:
    event = {"tool_name": tool, "tool_input": {"command": command}}
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
