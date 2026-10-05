#!/usr/bin/env python3
"""Claude Code PreToolUse hook: route every `git commit` to the human.

Backs GIT.md's manual-development rule ("the human commits unless they
explicitly ask"). Permission patterns such as `Bash(git commit *)` only match
commands that start with those words, so `git -C repo commit`, `cd x && git
commit`, or `env git -c k=v commit` slip past them. This hook parses the shell
command, finds each git invocation, skips git's global options, and answers
"ask" when the subcommand is `commit`. Interactive sessions show a permission
prompt; non-interactive sessions cannot be approved, so the commit is refused.

Reads the hook event JSON on stdin. Standard library only. Allows (no output)
anything it does not recognise as a commit; it is a guard, not a sandbox.
"""

import json
import os
import re
import shlex
import sys

_SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", "|&", ";;"}
_WRAPPERS = {"sudo", "env", "command", "exec", "nice", "time", "xargs", "nohup"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}


def _git_subcommand(args: list[str]) -> str | None:
    """Subcommand of `git <args>`, skipping global options."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        option = args[index]
        index += 2 if option in _GIT_VALUE_OPTIONS else 1
    return args[index] if index < len(args) else None


def commits(command: str) -> bool:
    """True when any simple command in the shell line runs `git ... commit`."""
    try:
        lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return "commit" in command and "git" in command  # unparseable: be conservative
    segment: list[str] = []
    for token in tokens + [";"]:
        if token in _SEPARATORS or set(token) <= set("&|;()"):
            words = [w for w in segment if not _ASSIGNMENT.match(w)]
            while words and words[0] in _WRAPPERS:
                words = words[1:]
            if words and os.path.basename(words[0]) == "git" and _git_subcommand(words[1:]) == "commit":
                return True
            segment = []
        else:
            segment.append(token)
    return False


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    if commits(str((event.get("tool_input") or {}).get("command", ""))):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "GIT.md manual mode: git commit needs explicit human approval "
                                        "(Autobuild checkpoints are made by its controller, not by agents).",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
