#!/usr/bin/env python3
"""Claude Code PreToolUse hook: route detected commits to human approval.

Backs GIT.md's manual-development rule ("the human commits unless they
explicitly ask"). Permission patterns such as `Bash(git commit *)` only match
commands that start with those words, so `git -C repo commit`, `cd x && git
commit`, or `env git -c k=v commit` slip past them. This hook parses the shell
command, skips Git's global options, and inspects visible aliases and small
explicit shell scripts. It answers "ask" for detected commits. Interactive
sessions show a permission prompt; unattended sessions without a permission
host cannot approve it, so the commit is refused.

Reads the hook event JSON on stdin. Standard library only. Allows (no output)
anything it does not recognise as a commit; it is a guard, not a sandbox.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", "{", "}", "|&", ";;"}
_WRAPPERS = {"sudo", "env", "command", "exec", "nice", "time", "xargs", "nohup"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_GIT = shutil.which("git")
_READ_COMMANDS = {"status", "diff", "log", "show", "config", "rev-parse", "ls-files", "ls-tree", "check-ignore", "help", "version"}


def _git_subcommand_index(args: list[str]) -> int:
    """Index of the subcommand, skipping Git's global options."""
    index = 0
    while index < len(args) and args[index].startswith("-"):
        option = args[index]
        index += 2 if option in _GIT_VALUE_OPTIONS else 1
    return index


def _git_commits(words: list[str], cwd: Path, environment: dict[str, str], depth: int) -> bool:
    """Read aliases using Git's config parser; never execute an alias."""
    index = 1 + _git_subcommand_index(words[1:])
    subcommand = words[index] if index < len(words) else None
    if subcommand == "commit":
        return True
    if not subcommand or subcommand in _READ_COMMANDS or not _GIT or depth >= 6:
        return False
    options = words[1:index]
    # --exec-path affects external subcommands, not alias config resolution.
    config_options = []
    position = 0
    while position < len(options):
        option = options[position]
        count = 2 if option in _GIT_VALUE_OPTIONS else 1
        if option in ("-C", "-c", "--git-dir", "--work-tree", "--config-env") or option.startswith(
                ("-C", "-c", "--git-dir=", "--work-tree=", "--config-env=")):
            config_options.extend(options[position:position + count])
        position += count
    try:
        result = subprocess.run([_GIT, *config_options, "config", "--get", f"alias.{subcommand}"],
                                cwd=cwd, env=environment, capture_output=True, text=True, timeout=1)
    except (OSError, subprocess.TimeoutExpired):
        return False
    alias = result.stdout.strip() if result.returncode == 0 else ""
    if not alias:
        return False
    effective_cwd = cwd
    for position, option in enumerate(options):
        if option == "-C" and position + 1 < len(options):
            effective_cwd = (effective_cwd / options[position + 1]).resolve()
        elif option.startswith("-C") and len(option) > 2:
            effective_cwd = (effective_cwd / option[2:]).resolve()
    if alias.startswith("!"):
        try:
            root = subprocess.run([_GIT, *config_options, "rev-parse", "--show-toplevel"], cwd=cwd,
                                  env=environment, capture_output=True, text=True, timeout=1)
            if root.returncode == 0:
                effective_cwd = Path(root.stdout.strip())
        except (OSError, subprocess.TimeoutExpired):
            pass
        return commits(alias[1:], effective_cwd, environment, depth + 1)
    return commits("git " + shlex.join(options) + " " + alias, cwd, environment, depth + 1)


def _shell_script(path: str, cwd: Path, environment: dict[str, str], depth: int) -> bool:
    """Inspect small explicit shell scripts; do not resolve arbitrary PATH tools."""
    if depth >= 6:
        return False
    source = cwd / path
    try:
        if not source.is_file() or source.stat().st_size > 65536:
            return False
        content = source.read_text()
    except (OSError, UnicodeError):
        return False
    first = content.splitlines()[0] if content else ""
    if source.suffix != ".sh" and not (first.startswith("#!") and any(shell in first for shell in _SHELLS)):
        return False
    return commits(content, cwd, environment, depth + 1)


def commits(command: str, cwd: Path | None = None, environment: dict[str, str] | None = None, depth: int = 0) -> bool:
    """Detect direct commits, visible aliases, shell -c and explicit shell scripts."""
    if depth >= 6:
        return False
    cwd = cwd or Path.cwd()
    environment = dict(os.environ if environment is None else environment)
    try:
        lexer = shlex.shlex(command.replace("\n", "\n ; \n"), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return "commit" in command and "git" in command  # unparseable: be conservative
    segment: list[str] = []
    for token in tokens + [";"]:
        if token in _SEPARATORS or set(token) <= set("&|;()"):
            words = list(segment)
            local_env = dict(environment)
            while words:
                if _ASSIGNMENT.match(words[0]):
                    name, value = words.pop(0).split("=", 1)
                    local_env[name] = value
                elif os.path.basename(words[0]) in _WRAPPERS:
                    wrapper = os.path.basename(words.pop(0))
                    while words and words[0].startswith("-"):
                        option = words.pop(0)
                        if option in ("-u", "--unset", "-n", "--adjustment", "-a", "-P", "-I") and words:
                            value = words.pop(0)
                            if wrapper == "env" and option in ("-u", "--unset"):
                                local_env.pop(value, None)
                        if wrapper == "env" and option in ("-i", "--ignore-environment"):
                            local_env.clear()
                else:
                    break
            if words:
                executable = os.path.basename(words[0])
                if executable == "git" and _git_commits(words, cwd, local_env, depth):
                    return True
                if executable in _SHELLS:
                    for position, word in enumerate(words[1:], start=1):
                        if word.startswith("-") and "c" in word[1:] and position + 1 < len(words):
                            if commits(words[position + 1], cwd, local_env, depth + 1):
                                return True
                            break
                        if not word.startswith("-"):
                            if _shell_script(word, cwd, local_env, depth):
                                return True
                            break
                elif executable == "alias":
                    for definition in words[1:]:
                        if "=" in definition and commits(definition.split("=", 1)[1], cwd, local_env, depth + 1):
                            return True
                elif "/" in words[0] and _shell_script(words[0], cwd, local_env, depth):
                    return True
                if executable == "cd" and len(words) == 2:
                    cwd = (cwd / os.path.expanduser(words[1])).resolve()
            elif segment and _ASSIGNMENT.match(segment[0]):
                environment.update(local_env)
            segment = []
        else:
            segment.append(token)
    return False


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return 0
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    if commits(str(tool_input.get("command", "")), Path(event.get("cwd") or Path.cwd())):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": "GIT.md manual mode: git commit needs explicit human approval "
                                        "(Autobuild checkpoints are made by its controller, not by agents).",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
