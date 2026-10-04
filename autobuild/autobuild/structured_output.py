"""Turn an agent's final message into the structured report the controller asked for."""

import json
import re
from typing import Any, Mapping, Optional

from jsonschema import Draft202012Validator

_FENCE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def parse_report(text: Optional[str], schema: Mapping[str, Any]) -> tuple[Optional[dict], Optional[str]]:
    """Return (report, error). Accepts bare JSON or one fenced JSON block."""
    if text is None or not text.strip():
        return None, "agent produced no final message"
    candidate = text.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        report = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return None, f"final message is not JSON: {exc}"
    return validate_report(report, schema)


def validate_report(report: Any, schema: Mapping[str, Any]) -> tuple[Optional[dict], Optional[str]]:
    """Return (report, None) when `report` satisfies `schema`, else (None, error)."""
    errors = sorted(Draft202012Validator(schema).iter_errors(report), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        location = "/".join(str(p) for p in first.absolute_path) or "<root>"
        return None, f"report does not match schema at {location}: {first.message}"
    return report, None


def strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of `schema` without top-level annotation keys that strict structured-output APIs reject."""
    return {k: v for k, v in schema.items() if k not in ("$schema", "$id", "title", "description")}
