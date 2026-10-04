#!/usr/bin/env python3
"""Audit the global instruction chain for every supported runtime.

For each canonical policy in policies/global/, verify that:
  1. ~/.agents/<NAME>.md is a symlink resolving to the canonical file;
  2. the Claude Code adapter (~/.claude/CLAUDE.md) imports it (`@~/.agents/<NAME>.md`);
  3. the Codex adapter (~/.codex/AGENTS.md) references it (`~/.agents/<NAME>.md`).
Also flags canonical policies that contain auto-memory records (they belong
in the agent's memory store, not in vendor-neutral policy).

Read-only. Exit 0 when the chain is complete, 1 otherwise. Standard library
only, so it runs on a fresh machine before any virtualenv exists.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / "policies" / "global"
RUNTIME_DIR = Path.home() / ".agents"
ADAPTERS = {
    "claude": (Path.home() / ".claude" / "CLAUDE.md", "@~/.agents/{name}.md"),
    "codex": (Path.home() / ".codex" / "AGENTS.md", "~/.agents/{name}.md"),
}
# Markers of an auto-memory file pasted into a policy.
_MEMORY_MARKERS = re.compile(r"^\s*(originSessionId:|node_type: memory)", re.M)


def audit() -> list[str]:
    problems = []
    policies = sorted(p.stem for p in POLICY_DIR.glob("*.md"))
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


def main() -> int:
    problems = audit()
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        names = ", ".join(sorted(p.stem for p in POLICY_DIR.glob("*.md")))
        print(f"OK   {len(ADAPTERS)} runtime adapters load all global policies: {names}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
