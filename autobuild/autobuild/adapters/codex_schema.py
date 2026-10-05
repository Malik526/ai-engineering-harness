"""Project the full contract into the structured-output API's supported shape.

Conditional constraints remain authoritative in local validation.
Optional fields are required nullable fields on the wire, then omitted when null.
"""

import copy


def output_schema(schema: dict) -> dict:
    allowed = {"type", "enum", "properties", "required", "additionalProperties", "items", "$defs", "$ref", "anyOf",
               "pattern", "format", "minimum", "maximum", "minItems", "maxItems", "minLength", "maxLength"}
    projected = {key: copy.deepcopy(value) for key, value in schema.items() if key in allowed}
    if "const" in schema:
        projected["enum"] = [schema["const"]]
    if "enum" in projected and "type" not in projected:
        value = projected["enum"][0]
        projected["type"] = "string" if isinstance(value, str) else "integer"
    if "properties" in projected:
        required = set(schema.get("required", []))
        properties = {}
        for name, child in schema["properties"].items():
            shape = output_schema(child)
            properties[name] = shape if name in required else {"anyOf": [shape, {"type": "null"}]}
        projected.update(properties=properties, required=list(properties), additionalProperties=False)
    if "items" in projected:
        projected["items"] = output_schema(schema["items"])
    for key in ("$defs",):
        if key in projected:
            projected[key] = {name: output_schema(child) for name, child in schema[key].items()}
    if "anyOf" in schema:
        projected["anyOf"] = [output_schema(child) for child in schema["anyOf"]]
    return projected


def omit_optional_nulls(value, schema: dict):
    if isinstance(value, dict):
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        return {name: omit_optional_nulls(child, properties.get(name, {})) for name, child in value.items()
                if name in required or child is not None}
    if isinstance(value, list):
        return [omit_optional_nulls(child, schema.get("items", {})) for child in value]
    return value
