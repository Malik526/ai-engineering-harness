"""Split a Markdown document into YAML front matter and body."""

from typing import Any

from autobuild.common.yaml_loader import load_yaml

_DELIMITER = "---"


class FrontMatterError(ValueError):
    """The document has no parseable YAML front matter mapping."""


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Return (metadata, body) for a document that starts with a `---` YAML block."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _DELIMITER:
        raise FrontMatterError("document must start with a '---' YAML front matter block")
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIMITER:
            meta = load_yaml("".join(lines[1:index]))
            if not isinstance(meta, dict):
                raise FrontMatterError("front matter must be a YAML mapping")
            return meta, "".join(lines[index + 1 :])
    raise FrontMatterError("front matter block is not closed with '---'")
