"""Safe YAML loading that keeps dates as strings.

PyYAML's SafeLoader turns `2026-10-03` into a `datetime.date`, which then
fails JSON-schema string checks with a confusing message. Every autobuild YAML
document (config, brief front matter, policy) is loaded through here instead.
"""

from typing import Any

import yaml

_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader without the implicit timestamp resolver."""


_StringDateLoader.yaml_implicit_resolvers = {
    first_char: [r for r in resolvers if r[0] != _TIMESTAMP_TAG]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(text: str) -> Any:
    """Parse YAML text with safe semantics and string-valued dates."""
    return yaml.load(text, Loader=_StringDateLoader)  # noqa: S506 — SafeLoader subclass
