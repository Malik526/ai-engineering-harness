"""Known agent providers and resolution of a project's role assignments.

providers/registry.yaml is the only place concrete providers are named. This
module turns a project's `agents` / `providers` config into one
RoleAssignment per role, so the controller can invoke "the reviewer" without
knowing which provider that is.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

from autobuild.common.paths import PROVIDERS_DIR
from autobuild.core.roles import ROLES
from autobuild.common.yaml_loader import load_yaml


@dataclass(frozen=True)
class RoleAssignment:
    role: str
    provider: str  # registry id
    display_name: str
    command: str  # executable to run (project override or registry default)
    model: Optional[str]  # None = provider default


@lru_cache(maxsize=None)
def load_registry() -> dict[str, Any]:
    """Return providers/registry.yaml as a dict."""
    return load_yaml((PROVIDERS_DIR / "registry.yaml").read_text())


def assignment_errors(config_data: dict[str, Any], registry: Optional[dict[str, Any]] = None) -> list[str]:
    """Unknown providers, providers that do not support their role, and overrides for unknown providers."""
    providers = (registry or load_registry())["providers"]
    errors = []
    for role in ROLES:
        provider = config_data["agents"][role]["provider"]
        if provider not in providers:
            errors.append(f"agents.{role}: unknown provider {provider!r}; known: {', '.join(sorted(providers))}")
        elif role not in providers[provider]["roles"]:
            errors.append(f"agents.{role}: provider {provider!r} does not support the {role} role")
    for provider in config_data.get("providers", {}):
        if provider not in providers:
            errors.append(f"providers.{provider}: unknown provider")
    return errors


def resolve_assignments(
    config_data: dict[str, Any], registry: Optional[dict[str, Any]] = None
) -> dict[str, RoleAssignment]:
    """Map each role to its provider, applying project overrides. Assumes validated config."""
    return {role: assignment_for(config_data, role, config_data["agents"][role]["provider"], registry)
            for role in ROLES}


def assignment_for(config_data: dict[str, Any], role: str, provider: str,
                   registry: Optional[dict[str, Any]] = None) -> RoleAssignment:
    """`provider` in `role` with project overrides applied (also used for configured rollover replacements)."""
    entry = (registry or load_registry())["providers"][provider]
    override = config_data.get("providers", {}).get(provider, {})
    return RoleAssignment(role=role, provider=provider, display_name=entry["display_name"],
                          command=override.get("command", entry["executable"]), model=override.get("model"))
