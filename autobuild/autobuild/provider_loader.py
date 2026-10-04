"""Instantiate the adapter for a role assignment from the registry's `adapter` entry.

Core code never imports a provider adapter by name: the registry maps each
provider id to a 'module:Class' path, loaded here.
"""

import importlib
from typing import Any, Optional

from autobuild.agent_provider import AgentProvider
from autobuild import provider_registry
from autobuild.provider_registry import RoleAssignment


class ProviderLoadError(RuntimeError):
    """The registry entry has no usable adapter."""


def load_adapter(assignment: RoleAssignment, registry: Optional[dict[str, Any]] = None) -> AgentProvider:
    """Return a ready-to-use adapter for `assignment`."""
    entry = (registry or provider_registry.load_registry())["providers"].get(assignment.provider)
    if entry is None:
        raise ProviderLoadError(f"provider {assignment.provider!r} is not in the registry")
    target = entry.get("adapter")
    if not target or ":" not in target:
        raise ProviderLoadError(f"provider {assignment.provider!r} has no 'module:Class' adapter in the registry")
    module_name, class_name = target.split(":", 1)
    try:
        adapter_class = getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError) as exc:
        raise ProviderLoadError(f"cannot load adapter {target!r} for {assignment.provider!r}: {exc}") from exc
    return adapter_class(assignment)
