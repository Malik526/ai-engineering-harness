"""Read the policy YAML files in policy/."""

from functools import lru_cache
from typing import Any

from autobuild.common.paths import POLICY_DIR
from autobuild.common.yaml_loader import load_yaml


@lru_cache(maxsize=None)
def load_policy(name: str) -> dict[str, Any]:
    """Return policy/<name>.yaml as a dict."""
    return load_yaml((POLICY_DIR / f"{name}.yaml").read_text())
