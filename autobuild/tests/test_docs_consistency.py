"""Documentation agrees with the code, schemas, and policy it describes."""

import re

from autobuild.core.artifacts import RUN_ARTIFACTS
from autobuild.core.config import config_errors
from autobuild.control.control import STOP_SEQUENCE
from autobuild.common.paths import DOCS_DIR, TEMPLATE_DIR
from autobuild.policy.policy_loader import load_policy
from autobuild.common.schemas import load_schema
from autobuild.core.states import RunState
from autobuild.common.yaml_loader import load_yaml


def _doc(name: str) -> str:
    return (DOCS_DIR / name).read_text()


def test_architecture_lists_every_state():
    text = _doc("architecture/ARCHITECTURE.md")
    for state in RunState:
        assert f"`{state.value}`" in text, state


def test_autonomy_policy_doc_covers_classes_and_conditions():
    text = _doc("safety/AUTONOMY_POLICY.md")
    policy = load_policy("autonomy")
    for cls in load_schema("implementation")["properties"]["autonomy"]["enum"]:
        assert f"## {cls.upper()}" in text
    assert set(policy["classes"]) == {"green", "yellow", "red"}
    for condition in policy["start_conditions"]:
        assert f"`{condition}`" in text, condition


def test_safety_doc_lists_every_operation():
    text = _doc("safety/SAFETY_MODEL.md")
    policy = load_policy("safety")
    for op in policy["allowed"] + policy["prohibited"]:
        assert f"`{op}`" in text, op


def test_artifact_doc_matches_contract_table():
    rows = {
        m.group(1): (m.group(2), m.group(3))
        for m in re.finditer(r"^\| `([^`]+)` \| (\w+) \| (\w+) \|", _doc("contracts/ARTIFACT_CONTRACT.md"), re.M)
    }
    assert rows == {a.path: (a.authority, a.producer) for a in RUN_ARTIFACTS}


def test_control_doc_lists_stop_sequence_in_order():
    text = _doc("contracts/CONTROL_CONTRACT.md")
    positions = [text.index(f"`{step}`") for step in STOP_SEQUENCE]
    assert positions == sorted(positions)


def test_brief_template_front_matter_is_valid_draft():
    from autobuild.common.front_matter import split_front_matter
    from autobuild.policy.implementations import brief_errors

    meta, body = split_front_matter((TEMPLATE_DIR / "implementation-brief.md").read_text())
    assert brief_errors(meta, body) == []


def test_starter_config_is_valid():
    assert config_errors(load_yaml((TEMPLATE_DIR / "project-config.yaml").read_text())) == []


# --- Layout: keep docs and the package grouped by responsibility ---

DOC_FOLDERS = {"architecture", "operations", "contracts", "safety", "evaluations", "decisions"}
PACKAGE_FOLDERS = {"common", "core", "policy", "providers", "rollover", "git", "validation", "review", "governance",
                   "control", "notifications"}
PACKAGE_ROOT_MODULES = {"__init__.py", "__main__.py", "cli.py", "fixtures.py"}


def test_docs_live_in_category_folders():
    entries = {p.name for p in DOCS_DIR.iterdir() if not p.name.startswith(".")}
    assert entries == DOC_FOLDERS | {"README.md"}, "new documentation belongs in a category folder (docs/README.md)"
    index = (DOCS_DIR / "README.md").read_text()
    assert all(f"]({folder}/)" in index for folder in DOC_FOLDERS)


def test_relative_doc_links_resolve():
    from autobuild.common.paths import CORE_ROOT
    broken = []
    for path in [CORE_ROOT / "README.md", *DOCS_DIR.rglob("*.md")]:
        for target in re.findall(r"\]\((?!https?://|#|mailto:)([^)#\s]+)", path.read_text()):
            if not (path.parent / target).exists():
                broken.append(f"{path.relative_to(CORE_ROOT)} -> {target}")
    assert broken == []


def test_package_modules_live_in_responsibility_packages():
    from autobuild.common.paths import CORE_ROOT
    package = CORE_ROOT / "autobuild"
    root_modules = {p.name for p in package.glob("*.py")}
    folders = {p.name for p in package.iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert root_modules == PACKAGE_ROOT_MODULES, "new modules belong in a responsibility package (see autobuild/__init__.py)"
    assert folders == PACKAGE_FOLDERS
    assert all((package / folder / "__init__.py").is_file() for folder in folders)
