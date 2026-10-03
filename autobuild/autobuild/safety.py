"""Protected-branch and operation checks from policy/safety.yaml.

Operations are default-deny: anything not explicitly allowed is refused. These
checks are the policy layer only; phase 0.2 adds hard enforcement (agent tool
restrictions, worktree confinement) and GitHub branch protection is the
server-side backstop. See docs/SAFETY_MODEL.md.
"""

from typing import Any, Iterable

from autobuild.policy_loader import load_policy

_REF_PREFIXES = ("refs/heads/", "refs/remotes/origin/", "origin/")


def normalize_branch(branch: str) -> str:
    """Strip ref prefixes so 'refs/heads/main' and 'origin/main' compare as 'main'."""
    for prefix in _REF_PREFIXES:
        if branch.startswith(prefix):
            return branch[len(prefix) :]
    return branch


def is_protected_branch(branch: str, protected: Iterable[str]) -> bool:
    """True when `branch` names one of the protected branches."""
    return normalize_branch(branch) in {normalize_branch(p) for p in protected}


def is_operation_allowed(operation: str, policy: dict[str, Any] | None = None) -> bool:
    """True only for operations the safety policy explicitly allows."""
    policy = policy or load_policy("safety")
    return operation in policy["allowed"] and operation not in policy["prohibited"]
