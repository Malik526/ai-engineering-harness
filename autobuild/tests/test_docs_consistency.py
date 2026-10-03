"""Documentation agrees with the code, schemas, and policy it describes."""

import re

from autobuild.artifacts import RUN_ARTIFACTS
from autobuild.config import config_errors
from autobuild.control import STOP_SEQUENCE
from autobuild.paths import DOCS_DIR, TEMPLATE_DIR
from autobuild.policy_loader import load_policy
from autobuild.schemas import load_schema
from autobuild.states import RunState
from autobuild.yaml_loader import load_yaml


def _doc(name: str) -> str:
    return (DOCS_DIR / name).read_text()


def test_architecture_lists_every_state():
    text = _doc("ARCHITECTURE.md")
    for state in RunState:
        assert f"`{state.value}`" in text, state


def test_autonomy_policy_doc_covers_classes_and_conditions():
    text = _doc("AUTONOMY_POLICY.md")
    policy = load_policy("autonomy")
    for cls in load_schema("implementation")["properties"]["autonomy"]["enum"]:
        assert f"## {cls.upper()}" in text
    assert set(policy["classes"]) == {"green", "yellow", "red"}
    for condition in policy["start_conditions"]:
        assert f"`{condition}`" in text, condition


def test_safety_doc_lists_every_operation():
    text = _doc("SAFETY_MODEL.md")
    policy = load_policy("safety")
    for op in policy["allowed"] + policy["prohibited"]:
        assert f"`{op}`" in text, op


def test_artifact_doc_matches_contract_table():
    rows = {
        m.group(1): (m.group(2), m.group(3))
        for m in re.finditer(r"^\| `([^`]+)` \| (\w+) \| (\w+) \|", _doc("ARTIFACT_CONTRACT.md"), re.M)
    }
    assert rows == {a.path: (a.authority, a.producer) for a in RUN_ARTIFACTS}


def test_control_doc_lists_stop_sequence_in_order():
    text = _doc("CONTROL_CONTRACT.md")
    positions = [text.index(f"`{step}`") for step in STOP_SEQUENCE]
    assert positions == sorted(positions)


def test_brief_template_front_matter_is_valid_draft():
    from autobuild.front_matter import split_front_matter
    from autobuild.implementations import brief_errors

    meta, body = split_front_matter((TEMPLATE_DIR / "implementation-brief.md").read_text())
    assert brief_errors(meta, body) == []


def test_starter_config_is_valid():
    assert config_errors(load_yaml((TEMPLATE_DIR / "project-config.yaml").read_text())) == []
