"""Shared fixtures-as-functions: fresh copies of the example documents."""

import copy
import json
from typing import Any

from autobuild.policy.implementations import load_brief
from autobuild.common.paths import EXAMPLES_DIR, TEMPLATE_DIR
from autobuild.common.yaml_loader import load_yaml


def example_json(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES_DIR / name).read_text())


def example_brief(name: str) -> tuple[dict[str, Any], str]:
    meta, body = load_brief(EXAMPLES_DIR / "implementations" / name)
    return copy.deepcopy(meta), body


def starter_config() -> dict[str, Any]:
    return load_yaml((TEMPLATE_DIR / "project-config.yaml").read_text())
