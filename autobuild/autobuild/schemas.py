"""Load the core JSON schemas and validate documents against them.

Schemas live in schemas/<name>.schema.json and are checked for schema
validity on first load, so a broken schema fails loudly rather than silently
accepting everything.
"""

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from autobuild.paths import SCHEMA_DIR

SCHEMA_NAMES = ("config", "implementation", "run-state", "review", "validation", "notification")


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Return the parsed schema `name`, after confirming it is a valid 2020-12 schema."""
    if name not in SCHEMA_NAMES:
        raise KeyError(f"unknown schema {name!r}; expected one of {SCHEMA_NAMES}")
    schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return schema


def schema_errors(name: str, instance: Any) -> list[str]:
    """Return human-readable errors for `instance` against schema `name` (empty when valid)."""
    validator = Draft202012Validator(load_schema(name))
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [_format_error(e) for e in errors]


def _format_error(error: ValidationError) -> str:
    location = "/".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{location}: {error.message}"
