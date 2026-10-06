"""Filesystem locations inside the autobuild core.

Everything resolves relative to this package, so the core works from any
checkout location and from any project's working directory.
"""

from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[2]  # autobuild/autobuild/common/paths.py -> autobuild/
SCHEMA_DIR = CORE_ROOT / "schemas"
POLICY_DIR = CORE_ROOT / "policy"
TEMPLATE_DIR = CORE_ROOT / "templates"
DOCS_DIR = CORE_ROOT / "docs"
EXAMPLES_DIR = CORE_ROOT / "examples"
PROVIDERS_DIR = CORE_ROOT / "providers"

# Where a project keeps its autobuild config, relative to the project root.
PROJECT_CONFIG_RELPATH = Path(".autobuild") / "config.yaml"
