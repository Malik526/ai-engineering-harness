"""Role → provider assignment is configuration; core code never names a provider."""

import re

import pytest

from autobuild.config import config_errors
from autobuild.paths import CORE_ROOT
from autobuild.provider_registry import assignment_errors, load_registry, resolve_assignments
from autobuild.roles import ROLES
from helpers import starter_config


def _config(planner, implementer, reviewer, **providers):
    data = starter_config()
    data["agents"] = {"planner": {"provider": planner}, "implementer": {"provider": implementer},
                      "reviewer": {"provider": reviewer}}
    if providers:
        data["providers"] = providers
    return data


@pytest.mark.parametrize("assignment", [
    ("codex", "claude", "codex"),
    ("claude", "claude", "claude"),
    ("codex", "codex", "codex"),
    ("claude", "codex", "claude"),
])
def test_every_role_combination_is_valid(assignment):
    data = _config(*assignment)
    assert config_errors(data) == []
    resolved = resolve_assignments(data)
    assert tuple(resolved[role].provider for role in ROLES) == assignment


def test_registry_defaults_and_project_overrides():
    data = _config("codex", "claude", "codex", claude={"command": "/opt/bin/claude", "model": "some-model"})
    resolved = resolve_assignments(data)
    assert resolved["implementer"].command == "/opt/bin/claude"
    assert resolved["implementer"].model == "some-model"
    assert resolved["planner"].command == "codex" and resolved["planner"].model is None
    assert resolved["implementer"].display_name == "Claude Code"


def test_unknown_provider_rejected():
    errors = config_errors(_config("codex", "gemini", "codex"))
    assert any("agents.implementer: unknown provider 'gemini'" in e for e in errors)


def test_override_for_unknown_provider_rejected():
    errors = config_errors(_config("codex", "claude", "codex", other={"command": "x"}))
    assert any("providers.other" in e for e in errors)


def test_provider_must_support_role():
    registry = {"providers": {"reader": {"display_name": "Reader", "executable": "r", "roles": ["reviewer"]}}}
    data = _config("reader", "reader", "reader")
    errors = assignment_errors(data, registry)
    assert len(errors) == 2 and all("does not support" in e for e in errors)


def test_agents_block_required():
    data = starter_config()
    del data["agents"]
    assert any("agents" in e for e in config_errors(data))


def test_registry_roles_are_known_roles():
    for provider in load_registry()["providers"].values():
        assert set(provider["roles"]) <= set(ROLES)


def test_core_code_never_names_a_provider():
    """Orchestration code must work through roles; only the registry names providers."""
    names = re.compile("|".join(re.escape(p) for p in load_registry()["providers"]), re.I)
    offenders = [
        f"{path.relative_to(CORE_ROOT)}:{n}"
        for path in (CORE_ROOT / "autobuild").glob("*.py")
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if names.search(line)
    ]
    assert offenders == []
