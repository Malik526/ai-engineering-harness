#!/usr/bin/env python3
"""Audit the global instruction chain for every supported runtime.

For each canonical policy in policies/global/, verify that:
  1. ~/.agents/<NAME>.md is a symlink resolving to the canonical file;
  2. the Claude Code adapter (~/.claude/CLAUDE.md) imports it (`@~/.agents/<NAME>.md`);
  3. the Codex adapter (~/.codex/AGENTS.md) references it (`~/.agents/<NAME>.md`).
Also flags canonical policies that contain auto-memory records (they belong
in the agent's memory store, not in vendor-neutral policy), verifies that the
policy enforcement matrix covers every canonical policy, and checks the
runtime commit guards and adapter sections against the canonical runtime/
fragments. Only providers whose executables are installed are required.
Runtime results distinguish PASS, MISSING, CONFLICT, STALE and provider SKIP.

Read-only. Exit 0 when the chain is complete, 1 otherwise. Standard library
only, so it runs on a fresh machine before any virtualenv exists.
"""

import argparse
import re
import sys
from pathlib import Path

from runtime_guards import installed_providers, reconcile, runtime_directory

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / "policies" / "global"
POLICY_MATRIX = REPO_ROOT / "docs" / "POLICY_ENFORCEMENT_MATRIX.md"
RUNTIME_DIR = Path.home() / ".agents"
ADAPTERS = {
    "claude": (Path.home() / ".claude" / "CLAUDE.md", "@~/.agents/{name}.md"),
    "codex": (Path.home() / ".codex" / "AGENTS.md", "~/.agents/{name}.md"),
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


def audit(providers: list[str] | None = None) -> list[str]:
    problems = []
    policies = policy_names()
    if not policies:
        return [f"no canonical policies in {POLICY_DIR}"]
    adapter_text = {}
    for runtime, (path, _) in ADAPTERS.items():
        if providers is not None and runtime not in providers:
            continue
        if path.is_file():
            adapter_text[runtime] = path.read_text()
        else:
            problems.append(f"MISSING {runtime}: adapter {path} is missing")

    for name in policies:
        canonical = POLICY_DIR / f"{name}.md"
        link = RUNTIME_DIR / f"{name}.md"
        if not link.is_symlink():
            state = "CONFLICT" if link.exists() else "MISSING"
            problems.append(f"{state} {name}: {link} is not a symlink to the canonical policy")
        elif link.resolve() != canonical.resolve():
            problems.append(f"CONFLICT {name}: {link} resolves to {link.resolve()}, not {canonical}")
        for runtime, text in adapter_text.items():
            reference = ADAPTERS[runtime][1].format(name=name)
            if reference not in text:
                problems.append(f"STALE {name}: {runtime} adapter does not reference {reference}")
        if _MEMORY_MARKERS.search(canonical.read_text()):
            problems.append(f"CONFLICT {name}: canonical policy contains an auto-memory record")
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


def audit_commit_guards(providers: list[str] | None = None) -> list[str]:
    reports = reconcile(REPO_ROOT, RUNTIME_DIR.parent, providers if providers is not None else installed_providers())
    return [report for report in reports if report.startswith(("MISSING", "STALE", "CONFLICT"))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home(), help="target home for isolated audit")
    args = parser.parse_args()
    args.home = args.home.expanduser().resolve()
    global RUNTIME_DIR, ADAPTERS
    RUNTIME_DIR = args.home / ".agents"
    ADAPTERS = {
        "claude": (runtime_directory(args.home, "claude") / "CLAUDE.md", "@~/.agents/{name}.md"),
        "codex": (runtime_directory(args.home, "codex") / "AGENTS.md", "~/.agents/{name}.md"),
    }
    providers = installed_providers()
    problems = audit(providers) + audit_policy_matrix()
    for problem in problems:
        print(problem if problem.startswith(("MISSING", "STALE", "CONFLICT")) else f"MISSING {problem}")
    reports = reconcile(REPO_ROOT, args.home, providers)
    for report in reports:
        print(report)
    problems.extend(row for row in reports if row.startswith(("MISSING", "STALE", "CONFLICT")))
    if not problems:
        names = ", ".join(policy_names())
        print(f"PASS {len(providers)} installed runtime adapters reference all global policies: {names}")
        print(f"PASS policy enforcement matrix covers all global policies: {POLICY_MATRIX}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
