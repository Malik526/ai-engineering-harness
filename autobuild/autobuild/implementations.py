"""Load and validate implementation briefs (front matter + Markdown body)."""

from pathlib import Path
from typing import Any

from autobuild.front_matter import FrontMatterError, split_front_matter
from autobuild.schemas import schema_errors

# Body sections every brief must carry so the implementer and reviewer judge
# the same scope. Matches templates/implementation-brief.md.
REQUIRED_SECTIONS = ("## Objective", "## Scope", "## Non-Goals", "## Acceptance Criteria")


def load_brief(path: Path) -> tuple[dict[str, Any], str]:
    """Return (metadata, body) for the brief at `path`."""
    return split_front_matter(path.read_text())


def brief_errors(meta: dict[str, Any], body: str) -> list[str]:
    """Schema errors plus the rules JSON Schema cannot express."""
    errors = schema_errors("implementation", meta)
    if meta.get("id") in (meta.get("depends_on") or []):
        errors.append("depends_on: an implementation cannot depend on itself")
    for section in REQUIRED_SECTIONS:
        if section not in body:
            errors.append(f"body: missing required section '{section}'")
    return errors


def brief_file_errors(path: Path) -> list[str]:
    """Validate the brief at `path`, reporting front-matter problems as errors."""
    try:
        meta, body = load_brief(path)
    except FrontMatterError as exc:
        return [f"front matter: {exc}"]
    return brief_errors(meta, body)
