"""Instruction-chain audit coverage for policy wiring and matrix drift.

Run: autobuild/.venv/bin/python -m pytest scripts/tests
"""

import importlib.util
import json
from pathlib import Path

AUDIT = Path(__file__).resolve().parents[1] / "setup" / "audit_instructions.py"
POLICIES = ("CODING", "DOCUMENTATION", "EXECUTION", "GIT", "SECURITY", "VERIFICATION")


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_instructions", AUDIT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _configure_fake_install(module, monkeypatch, tmp_path, *, omit_from_matrix: str | None = None):
    repo = tmp_path / "repo"
    policy_dir = repo / "policies" / "global"
    policy_dir.mkdir(parents=True)
    docs = repo / "docs"
    docs.mkdir()
    home = tmp_path / "home"
    agents = home / ".agents"
    agents.mkdir(parents=True)

    for name in POLICIES:
        source = policy_dir / f"{name}.md"
        source.write_text(f"# {name}\n")
        (agents / f"{name}.md").symlink_to(source)

    claude_adapter = home / ".claude" / "CLAUDE.md"
    claude_adapter.parent.mkdir()
    claude_adapter.write_text("\n".join(f"@~/.agents/{name}.md" for name in POLICIES))
    codex_adapter = home / ".codex" / "AGENTS.md"
    codex_adapter.parent.mkdir()
    codex_adapter.write_text("\n".join(f"~/.agents/{name}.md" for name in POLICIES))

    claude_settings = home / ".claude" / "settings.json"
    claude_settings.write_text(json.dumps({
        "permissions": {"ask": ["Bash(git commit *)"]},
        "hooks": {"PreToolUse": [{
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "python3 /repo/scripts/hooks/git_commit_guard.py"}],
        }]},
    }))
    codex_rules = home / ".codex" / "rules" / "default.rules"
    codex_rules.parent.mkdir()
    codex_rules.write_text("\n".join([
        'prefix_rule(pattern=["git", "commit"], decision="prompt")',
        'prefix_rule(pattern=["git", "-C"], decision="prompt")',
        'prefix_rule(pattern=["git", "-c"], decision="prompt")',
    ]))

    matrix = docs / "POLICY_ENFORCEMENT_MATRIX.md"
    covered = [name for name in POLICIES if name != omit_from_matrix]
    matrix.write_text(
        "policy source\nclassification\ncurrent enforcement mechanism\n"
        "enforcement gap\nrecommended mechanism\nimplementation status\n"
        + "\n".join(f"policies/global/{name}.md" for name in covered)
    )

    monkeypatch.setattr(module, "REPO_ROOT", repo)
    monkeypatch.setattr(module, "POLICY_DIR", policy_dir)
    monkeypatch.setattr(module, "POLICY_MATRIX", matrix)
    monkeypatch.setattr(module, "RUNTIME_DIR", agents)
    monkeypatch.setattr(module, "ADAPTERS", {
        "claude": (claude_adapter, "@~/.agents/{name}.md"),
        "codex": (codex_adapter, "~/.agents/{name}.md"),
    })
    monkeypatch.setattr(module, "CLAUDE_SETTINGS", claude_settings)
    monkeypatch.setattr(module, "CODEX_RULES", codex_rules)


def test_instruction_audit_passes_complete_fake_install(tmp_path, monkeypatch):
    module = _load_module()
    _configure_fake_install(module, monkeypatch, tmp_path)

    assert module.audit() == []
    assert module.audit_policy_matrix() == []
    assert module.audit_commit_guards() == []


def test_instruction_audit_catches_policy_missing_from_matrix(tmp_path, monkeypatch):
    module = _load_module()
    _configure_fake_install(module, monkeypatch, tmp_path, omit_from_matrix="SECURITY")

    assert module.audit() == []
    assert module.audit_commit_guards() == []
    assert module.audit_policy_matrix() == [
        "policy matrix does not cover policies/global/SECURITY.md"
    ]
