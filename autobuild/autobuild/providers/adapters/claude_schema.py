"""Project a canonical report contract into the shape Claude Code's `--json-schema` accepts.

Claude Code turns the schema into a tool `input_schema`, and the API rejects
`oneOf`/`allOf`/`anyOf` (and other combinators) at the top level. The
projection removes only top-level annotations and combinators; every nested
constraint is kept. It may only relax the contract, never add to it: the
adapter validates the answer against the unchanged canonical schema, so the
dropped conditionals (for example "REVISE needs findings") stay authoritative.
"""

import copy
from typing import Any, Mapping

_ANNOTATIONS = ("$schema", "$id", "title", "description", "$comment", "examples")
_TOP_LEVEL_COMBINATORS = ("allOf", "anyOf", "oneOf", "not", "if", "then", "else")


class SchemaProjectionError(ValueError):
    """The canonical schema cannot be expressed as a Claude tool input schema."""


def input_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    if schema.get("type") != "object" or "$ref" in schema:
        raise SchemaProjectionError("a Claude structured-output schema must be a top-level object schema")
    return {key: copy.deepcopy(value) for key, value in schema.items()
            if key not in _ANNOTATIONS and key not in _TOP_LEVEL_COMBINATORS}
