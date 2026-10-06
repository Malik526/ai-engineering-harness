"""Load and validate a project's .autobuild/config.yaml."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autobuild.paths import PROJECT_CONFIG_RELPATH
from autobuild import provider_registry
from autobuild.provider_registry import RoleAssignment, assignment_errors, resolve_assignments
from autobuild.governance import governance_config_errors
from autobuild.rollover_policy import rollover_config_errors
from autobuild.schemas import schema_errors
from autobuild.yaml_loader import load_yaml
from autobuild.browser_contract import browser_config_errors
from autobuild.validation_contract import validation_config_errors


class ConfigError(ValueError):
    """The project config is missing or invalid; `errors` lists every problem."""

    def __init__(self, path: Path, errors: list[str]):
        super().__init__(f"{path}: " + "; ".join(errors))
        self.path = path
        self.errors = errors


@dataclass(frozen=True)
class ProjectConfig:
    """A validated project config plus the project root it belongs to."""

    root: Path
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return self.data["project"]["name"]

    @property
    def protected_branches(self) -> tuple[str, ...]:
        return tuple(self.data["git"]["protected_branches"])

    @property
    def branch_prefix(self) -> str:
        return self.data["git"]["branch_prefix"]

    @property
    def agents(self) -> dict[str, RoleAssignment]:
        """Role -> provider assignment, with project overrides applied."""
        return resolve_assignments(self.data)

    @property
    def max_review_cycles(self) -> int:
        return self.data["limits"]["max_review_cycles"]

    def path(self, key: str) -> Path:
        """Absolute path for one of the `paths` entries."""
        return self.root / self.data["paths"][key]


def config_errors(data: Any) -> list[str]:
    """Schema errors plus cross-field rules."""
    errors = schema_errors("config", data)
    if errors:
        return errors
    prefix = data["git"]["branch_prefix"]
    # An automation branch must never be able to share a name with a protected one.
    for protected in data["git"]["protected_branches"]:
        if protected.startswith(prefix):
            errors.append(f"git: protected branch {protected!r} falls under branch_prefix {prefix!r}")
    errors.extend(assignment_errors(data))
    errors.extend(rollover_config_errors(data, provider_registry.load_registry()["providers"]))
    errors.extend(governance_config_errors(data))
    errors.extend(browser_config_errors(data["validation"].get("browser_gates", [])))
    errors.extend(validation_config_errors(data["validation"]))
    return errors


def missing_paths(config: ProjectConfig) -> list[str]:
    """Configured paths that do not exist yet (a warning, not an error)."""
    return [f"paths.{key}: {config.path(key)}" for key in config.data["paths"] if not config.path(key).exists()]


def load_project_config(project_root: Path) -> ProjectConfig:
    """Read, validate, and return the config of the project at `project_root`."""
    path = project_root / PROJECT_CONFIG_RELPATH
    if not path.is_file():
        raise ConfigError(path, ["file not found"])
    data = load_yaml(path.read_text())
    errors = config_errors(data)
    if errors:
        raise ConfigError(path, errors)
    return ProjectConfig(root=project_root.resolve(), data=data)
