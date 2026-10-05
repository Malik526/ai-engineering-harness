"""Shared conservative filename guard; does not inspect or print credentials."""

import fnmatch
from pathlib import Path

# Files that must never leave the worktree in a diff or commit.
SECRET_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "credentials*.json",
                   "*service-account*.json", "auth.json")


def secret_like(paths: list[str]) -> list[str]:
    return [p for p in paths if any(fnmatch.fnmatch(Path(p).name, pattern) for pattern in SECRET_PATTERNS)]

