"""Deterministic checks on what an agent may do inside its worktree.

Used by the git shim on the agent's PATH (git_shim.py) and by provider
pre-tool hooks. Git is allow-listed: an agent may inspect history and edit
files, but only the controller creates commits or moves branches, so every
subcommand that writes refs, talks to a remote, or reconfigures the
repository is refused. File writes are confined to the worktree.

This is one layer of several (see docs/SAFETY_MODEL.md); a determined process
can call git by absolute path, which is why the controller also verifies the
protected refs before and after every agent operation.
"""

import os
import re
import shlex
from pathlib import Path
from typing import Callable, Optional

# --- Git allowlist ---

_READ_ONLY_FLAGS = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--show-origin", "--show-scope"}


def _branch_listing(args: list[str]) -> bool:
    listing_flags = {"-a", "--all", "-r", "--remotes", "-v", "-vv", "--list", "--show-current",
                     "--contains", "--merged", "--no-merged", "--no-color", "--color"}
    return all(a in listing_flags or a.startswith("--format") or a.startswith("--sort") for a in args)


def _config_read(args: list[str]) -> bool:
    return any(a in _READ_ONLY_FLAGS for a in args)


def _checkout_paths_only(args: list[str]) -> bool:
    # `git checkout -- <paths>` restores files; anything else may switch branches.
    return "--" in args and args.index("--") == 0


def _subcommand_listing(*allowed_first: str, bare_lists: bool = True) -> Callable[[list[str]], bool]:
    """Allow only the read-only sub-subcommands; a bare call is allowed only where it just lists."""
    return lambda args: (bare_lists and not args) or (bool(args) and args[0] in allowed_first)


_ALWAYS = lambda args: True  # noqa: E731

GIT_ALLOWED: dict[str, Callable[[list[str]], bool]] = {
    "status": _ALWAYS, "diff": _ALWAYS, "log": _ALWAYS, "show": _ALWAYS, "blame": _ALWAYS,
    "grep": _ALWAYS, "ls-files": _ALWAYS, "ls-tree": _ALWAYS, "cat-file": _ALWAYS,
    "rev-parse": _ALWAYS, "rev-list": _ALWAYS, "describe": _ALWAYS, "shortlog": _ALWAYS,
    "for-each-ref": _ALWAYS, "check-ignore": _ALWAYS, "check-attr": _ALWAYS, "merge-base": _ALWAYS,
    "name-rev": _ALWAYS, "var": _ALWAYS, "help": _ALWAYS, "version": _ALWAYS,
    "add": _ALWAYS, "rm": _ALWAYS, "mv": _ALWAYS, "restore": _ALWAYS,
    "branch": _branch_listing,
    "config": _config_read,
    "checkout": _checkout_paths_only,
    "remote": _subcommand_listing("-v", "--verbose", "show", "get-url"),
    "worktree": _subcommand_listing("list"),
    "stash": _subcommand_listing("list", "show", bare_lists=False),  # bare `git stash` saves and resets
    # Reading takes at most one positional (the ref name); writing takes two.
    "symbolic-ref": lambda args: len([a for a in args if not a.startswith("-")]) <= 1,
}

# Global options that take a value, so the subcommand comes later.
_GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_GIT_FORBIDDEN_OPTIONS = {"--git-dir", "--work-tree", "--namespace", "--exec-path"}


def check_git(args: list[str], worktree: Path, cwd: Optional[Path] = None) -> Optional[str]:
    """Return a refusal reason for `git <args>`, or None when the call is allowed."""
    cwd = cwd or Path.cwd()
    index = 0
    while index < len(args) and args[index].startswith("-"):
        option = args[index].split("=", 1)[0]
        if option in _GIT_FORBIDDEN_OPTIONS:
            return f"git option {option} is not allowed in autobuild runs"
        if option == "-C" and index + 1 < len(args):
            target = (cwd / args[index + 1]).resolve()
            if not is_within(target, worktree):
                return f"git -C {args[index + 1]} points outside the run worktree"
            cwd = target
        if option == "-c" and index + 1 < len(args) and args[index + 1].lower().startswith(("alias.", "core.hookspath")):
            return "git -c alias/hooksPath overrides are not allowed in autobuild runs"
        index += 2 if option in _GIT_VALUE_OPTIONS and "=" not in args[index] else 1
    if index >= len(args):
        return None  # bare `git` / `git --version`
    subcommand, rest = args[index], args[index + 1:]
    allowed = GIT_ALLOWED.get(subcommand)
    if allowed is None:
        return (f"`git {subcommand}` is not allowed for agents in autobuild runs: the controller owns commits, "
                "branches and remotes. Leave changes uncommitted in the worktree.")
    if not allowed(rest):
        return f"`git {subcommand} {' '.join(rest)}` is not allowed in autobuild runs (read-only forms only)."
    return None


# --- Shell commands (for pre-tool hooks) ---

_SEPARATORS = {"&&", "||", ";", "|", "&", "\n", "(", ")", "|&", ";;"}


def check_shell_command(command: str, worktree: Path, cwd: Optional[Path] = None) -> Optional[str]:
    """Best-effort scan of a shell command line for disallowed git invocations."""
    try:
        lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None  # unparseable quoting; the git shim still applies at execution time
    segment: list[str] = []
    for token in tokens + [";"]:
        if token in _SEPARATORS or set(token) <= set("&|;()"):
            reason = _check_segment(segment, worktree, cwd)
            if reason:
                return reason
            segment = []
        else:
            segment.append(token)
    return None


_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"sudo", "env", "command", "exec", "nice", "time", "xargs", "nohup"}


def _check_segment(segment: list[str], worktree: Path, cwd: Optional[Path]) -> Optional[str]:
    """Check one simple command, looking past VAR=value prefixes and wrapper commands."""
    for position, word in enumerate(segment):
        if _ASSIGNMENT.match(word) or word in _WRAPPERS:
            continue
        if os.path.basename(word) == "git":
            return check_git(segment[position + 1:], worktree, cwd)
        return None
    return None


# --- File writes ---

def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def check_file_write(path: str, worktree: Path) -> Optional[str]:
    """Refuse edits outside the worktree and to the worktree's git link file."""
    target = Path(path) if os.path.isabs(path) else worktree / path
    if not is_within(target, worktree):
        return f"writing {path} is outside the run worktree {worktree}"
    if target.resolve().relative_to(worktree.resolve()).parts[:1] == (".git",):
        return "writing git metadata is not allowed in autobuild runs"
    return None
