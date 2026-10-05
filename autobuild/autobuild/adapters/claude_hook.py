"""Claude Code PreToolUse hook enforcing the autobuild command guard.

Claude Code sends the pending tool call as JSON on stdin; exit code 2 blocks
the call and returns stderr to the model. The worktree comes from
AUTOBUILD_WORKTREE, set by the controller for the whole agent process.
"""

import json
import os
import sys
from pathlib import Path

from autobuild.command_guard import check_file_write, check_shell_command

_BLOCK = 2


def decide(event: dict, worktree: Path, role: str = "implementer") -> str | None:
    """Return a refusal reason for the tool call in `event`, or None to allow it."""
    tool = event.get("tool_name", "")
    if role == "reviewer" and tool in ("Bash", "Edit", "MultiEdit", "Write", "NotebookEdit", "TodoWrite"):
        return "reviewers have read access only"
    tool_input = event.get("tool_input") or {}
    if tool == "Bash":
        cwd = Path(event["cwd"]) if event.get("cwd") else worktree
        return check_shell_command(str(tool_input.get("command", "")), worktree, cwd)
    if tool in ("Edit", "MultiEdit", "Write", "NotebookEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return check_file_write(str(path), worktree) if path else None
    return None


def main() -> int:
    worktree = os.environ.get("AUTOBUILD_WORKTREE")
    if not worktree:
        print("autobuild guard: AUTOBUILD_WORKTREE not set; refusing tool call", file=sys.stderr)
        return _BLOCK
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("autobuild guard: unreadable hook input; refusing tool call", file=sys.stderr)
        return _BLOCK
    reason = decide(event, Path(worktree), os.environ.get("AUTOBUILD_ROLE", "implementer"))
    if reason:
        print(f"autobuild guard: {reason}", file=sys.stderr)
        return _BLOCK
    return 0


if __name__ == "__main__":
    sys.exit(main())
