#!/usr/bin/env python3
"""Audit the global instruction chain for every supported runtime.

For each canonical policy in policies/global/, verify that:
  1. ~/.agents/<NAME>.md is a symlink resolving to the canonical file;
  2. the Claude Code adapter (~/.claude/CLAUDE.md) imports it (`@~/.agents/<NAME>.md`);
  3. the Codex adapter (~/.codex/AGENTS.md) references it (`~/.agents/<NAME>.md`).
Also flags canonical policies that contain auto-memory records (they belong
in the agent's memory store, not in vendor-neutral policy), verifies that the
policy enforcement matrix covers every canonical policy, and checks the
runtime commit guards that back GIT.md's manual-mode rule: Claude Code must
ask before `git commit` (no silent allow rule, an ask rule, and the
scripts/hooks/git_commit_guard.py PreToolUse hook that also catches
`git -C ... commit`), and Codex's execpolicy rules must prompt for `git commit`,
`git -C` and `git -c`.

Read-only. Exit 0 when the chain is complete, 1 otherwise. Standard library
only, so it runs on a fresh machine before any virtualenv exists.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / "policies" / "global"
POLICY_MATRIX = REPO_ROOT / "docs" / "POLICY_ENFORCEMENT_MATRIX.md"
RUNTIME_DIR = Path.home() / ".agents"
ADAPTERS = {
    "claude": (Path.home() / ".claude" / "CLAUDE.md", "@~/.agents/{name}.md"),
    "codex": (Path.home() / ".codex" / "AGENTS.md", "~/.agents/{name}.md"),
}
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CODEX_RULES = Path.home() / ".codex" / "rules" / "default.rules"
COMMIT_HOOK = "git_commit_guard.py"
_CODEX_PROMPTS = {
    word: re.compile(r'prefix_rule\(\s*pattern\s*=\s*\[\s*"git"\s*,\s*"' + re.escape(word) + r'"\s*\]\s*,\s*decision\s*=\s*"prompt"')
    for word in ("commit", "-C", "-c")
}
# Markers of an auto-memory file pasted into a policy.
_MEMORY_MARKERS = re.compile(r"^\s*(originSessionId:|node_type: memory)", re.M)
_MATRIX_REQUIRED_TEXT = (
    "policy source",
    "classification",
    "current enforcement mechanism",
    "enforcement gap",
    "recommended mechanism",
    "implementation status",
)


def policy_names() -> list[str]:
    return sorted(p.stem for p in POLICY_DIR.glob("*.md"))


def audit() -> list[str]:
    problems = []
    policies = policy_names()
    if not policies:
        return [f"no canonical policies in {POLICY_DIR}"]
    adapter_text = {}
    for runtime, (path, _) in ADAPTERS.items():
        if path.is_file():
            adapter_text[runtime] = path.read_text()
        else:
            problems.append(f"{runtime}: adapter {path} is missing")

    for name in policies:
        canonical = POLICY_DIR / f"{name}.md"
        link = RUNTIME_DIR / f"{name}.md"
        if not link.is_symlink():
            problems.append(f"{name}: {link} is not a symlink to the canonical policy")
        elif link.resolve() != canonical.resolve():
            problems.append(f"{name}: {link} resolves to {link.resolve()}, not {canonical}")
        for runtime, text in adapter_text.items():
            reference = ADAPTERS[runtime][1].format(name=name)
            if reference not in text:
                problems.append(f"{name}: {runtime} adapter does not reference {reference}")
        if _MEMORY_MARKERS.search(canonical.read_text()):
            problems.append(f"{name}: canonical policy contains an auto-memory record")
    return problems


def audit_policy_matrix() -> list[str]:
    """The audit artifact must cover every canonical global policy."""
    policies = policy_names()
    if not POLICY_MATRIX.is_file():
        return [f"policy matrix {POLICY_MATRIX} is missing"]
    text = POLICY_MATRIX.read_text()
    normalized = text.lower()
    problems = [
        f"policy matrix is missing required field text: {required}"
        for required in _MATRIX_REQUIRED_TEXT
        if required not in normalized
    ]
    for name in policies:
        source = f"policies/global/{name}.md"
        if source not in text:
            problems.append(f"policy matrix does not cover {source}")
    return problems


def audit_commit_guards() -> list[str]:
    """Manual mode never commits silently: each runtime must stop for the human."""
    problems = []
    try:
        permissions = json.loads(CLAUDE_SETTINGS.read_text()).get("permissions", {})
    except (OSError, json.JSONDecodeError) as exc:
        return [f"claude: cannot read {CLAUDE_SETTINGS}: {exc}"]
    silent = [rule for rule in permissions.get("allow", []) if re.search(r"\bgit\s+commit\b|^Bash\(git\s*\*?\)$|^Bash$", rule)]
    if silent:
        problems.append(f"claude: allow rules let git commit run without asking: {', '.join(silent)}")
    if not any(re.search(r"\bgit\s+commit\b", rule) for rule in permissions.get("ask", [])):
        problems.append("claude: no ask rule for git commit in ~/.claude/settings.json")
    hooks = json.loads(CLAUDE_SETTINGS.read_text()).get("hooks", {}).get("PreToolUse", [])
    if not any(COMMIT_HOOK in h.get("command", "") for entry in hooks if entry.get("matcher") in ("Bash", "*")
               for h in entry.get("hooks", [])):
        problems.append(f"claude: PreToolUse Bash hook {COMMIT_HOOK} is not registered")
    try:
        rules = CODEX_RULES.read_text()
        missing = [word for word, pattern in _CODEX_PROMPTS.items() if not pattern.search(rules)]
        if missing:
            problems.append(f"codex: {CODEX_RULES} has no prompt rule for git {', git '.join(missing)}")
    except OSError:
        problems.append(f"codex: {CODEX_RULES} is missing")
    return problems


def main() -> int:
    problems = audit() + audit_policy_matrix() + audit_commit_guards()
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        names = ", ".join(policy_names())
        print(f"OK   {len(ADAPTERS)} runtime adapters load all global policies: {names}")
        print(f"OK   policy enforcement matrix covers all global policies: {POLICY_MATRIX}")
        print("OK   runtime commit guards: Claude Code (ask rule + hook) and Codex (prompt rules) stop before git commit")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
