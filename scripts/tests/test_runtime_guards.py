"""Fresh-home installation, ownership, drift and conflict regression tests."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/setup"))
from runtime_guards import reconcile


@pytest.mark.parametrize("providers", [[], ["claude"], ["codex"], ["claude", "codex"]])
def test_fresh_install_check_and_audit(tmp_path, providers):
    home, bin_dir = tmp_path / "home", tmp_path / "bin"
    bin_dir.mkdir()
    for provider in providers:
        executable = bin_dir / provider
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o700)
    env = {**os.environ, "PATH": str(bin_dir)}
    def run(script, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/setup" / script), "--home", str(home), *args],
                              env=env, capture_output=True, text=True)
    before = run("install.py", "--check")
    assert before.returncode == 1
    assert not home.exists()
    apply = run("install.py", "--apply")
    assert apply.returncode == 0, apply.stdout + apply.stderr
    check = run("install.py", "--check")
    assert check.returncode == 0, check.stdout + check.stderr
    again = run("install.py", "--apply")
    assert again.returncode == 0 and "UPDATED" not in again.stdout and "LINKED" not in again.stdout
    audit = run("audit_instructions.py")
    assert audit.returncode == 0, audit.stdout + audit.stderr
    assert (home / ".agents/GIT.md").is_symlink()
    for provider in ("claude", "codex"):
        assert (home / f".{provider}").exists() == (provider in providers)
    command = home / ".local/bin/autobuild"
    assert command.is_symlink() and command.resolve() == (ROOT / "autobuild/bin/autobuild").resolve()
    assert "is not on PATH" in apply.stdout  # reported, never fixed by editing shell files
    assert not (home / ".bashrc").exists() and not (home / ".profile").exists()


def test_autobuild_command_runs_from_any_directory_when_on_path(tmp_path):
    home = tmp_path / "home"
    env = {**os.environ, "PATH": f"{home / '.local/bin'}{os.pathsep}{os.environ['PATH']}"}
    apply = subprocess.run([sys.executable, str(ROOT / "scripts/setup/install.py"), "--home", str(home), "--apply"],
                           env=env, capture_output=True, text=True)
    assert f"{home / '.local/bin'} is on PATH" in apply.stdout
    done = subprocess.run(["autobuild", "check"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert done.returncode == 0 and "OK   schema config" in done.stdout, done.stdout + done.stderr


def test_existing_autobuild_command_is_never_overwritten(tmp_path):
    home = tmp_path / "home"
    existing = home / ".local/bin/autobuild"
    existing.parent.mkdir(parents=True)
    existing.write_text("#!/bin/sh\necho someone else's autobuild\n")
    apply = subprocess.run([sys.executable, str(ROOT / "scripts/setup/install.py"), "--home", str(home), "--apply"],
                           capture_output=True, text=True)
    assert apply.returncode == 1 and f"CONFLICT  {existing}" in apply.stdout
    assert existing.read_text() == "#!/bin/sh\necho someone else's autobuild\n" and not existing.is_symlink()


def setup(home, providers):
    reports = reconcile(ROOT, home, providers, apply=True)
    assert not any(row.startswith("CONFLICT") for row in reports), reports


def test_preserves_unrelated_settings_rules_adapters_and_modes(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    settings = claude / "settings.json"
    original = {"model": "personal-choice", "permissions": {"allow": ["Bash(npm test *)"]},
                "hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "personal-hook"}]}]}}
    settings.write_text(json.dumps(original))
    settings.chmod(0o640)
    (claude / "CLAUDE.md").write_text("Personal routing\n")
    rules = tmp_path / ".codex/rules/default.rules"
    rules.parent.mkdir(parents=True)
    original_rules = 'prefix_rule(pattern=["npm", "test"], decision="allow")\n'
    rules.write_text(original_rules)
    setup(tmp_path, ["claude", "codex"])
    merged = json.loads(settings.read_text())
    assert merged["model"] == original["model"]
    assert merged["permissions"]["allow"] == original["permissions"]["allow"]
    assert merged["hooks"]["PreToolUse"][0] == original["hooks"]["PreToolUse"][0]
    assert settings.stat().st_mode & 0o777 == 0o640
    assert rules.read_text().startswith(original_rules)
    assert (claude / "CLAUDE.md").read_text().startswith("Personal routing\n")
    snapshot = settings.read_bytes(), rules.read_bytes()
    setup(tmp_path, ["claude", "codex"])
    assert snapshot == (settings.read_bytes(), rules.read_bytes())


@pytest.mark.parametrize("rule", ["Bash", "Bash(*)", "Bash(git *)", "Bash(git:*)", "Bash(git commit *)", "Bash(git * commit *)",
                                 "Bash(git commit -m 'specific message')", "Bash(git -C /other commit -m specific)"])
def test_conflicting_claude_allow_is_reported_without_overwrite(tmp_path, rule):
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(json.dumps({"permissions": {"allow": [rule]}}))
    before = settings.read_bytes()
    reports = reconcile(ROOT, tmp_path, ["claude"], apply=True)
    assert any(row.startswith("CONFLICT claude") for row in reports)
    assert settings.read_bytes() == before
    assert not (settings.parent / "CLAUDE.md").exists()


@pytest.mark.parametrize("content", ["[]", "not json", '{"hooks":{"PreToolUse":{}}}', '{"disableAllHooks":true}',
                                    '{"permissions":{"defaultMode":"bypassPermissions"}}',
                                    '{"permissions":{"defaultMode":"dontAsk"}}'])
def test_invalid_or_disabled_claude_settings_refused(tmp_path, content):
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text(content)
    assert any(row.startswith("CONFLICT") for row in reconcile(ROOT, tmp_path, ["claude"], apply=True))
    assert settings.read_text() == content


def test_conflict_does_not_block_other_provider(tmp_path):
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.write_text('{"permissions":{"allow":["Bash"]}}')
    reports = reconcile(ROOT, tmp_path, ["claude", "codex"], apply=True)
    assert any(row.startswith("CONFLICT claude") for row in reports)
    assert (tmp_path / ".codex/rules/default.rules").read_text() == (ROOT / "runtime/codex/default.rules").read_text()


def test_hook_removal_and_canonical_path_drift_are_detected(tmp_path):
    setup(tmp_path, ["claude"])
    path = tmp_path / ".claude/settings.json"
    settings = json.loads(path.read_text())
    settings["hooks"]["PreToolUse"] = []
    path.write_text(json.dumps(settings))
    assert any(row.startswith("MISSING claude") for row in reconcile(ROOT, tmp_path, ["claude"]))
    setup(tmp_path, ["claude"])
    settings = json.loads(path.read_text())
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = "python3 /other/git_commit_guard.py # AI Engineering Harness: commit guard"
    path.write_text(json.dumps(settings))
    assert any(row.startswith("STALE claude") for row in reconcile(ROOT, tmp_path, ["claude"]))
    setup(tmp_path, ["claude"])
    assert all(not row.startswith(("MISSING", "STALE", "CONFLICT")) for row in reconcile(ROOT, tmp_path, ["claude"]))


def test_codex_drift_and_other_loaded_file_conflict(tmp_path):
    setup(tmp_path, ["codex"])
    rules = tmp_path / ".codex/rules/default.rules"
    rules.write_text(rules.read_text().replace('decision="prompt"', 'decision="allow"'))
    assert any(row.startswith("STALE codex") for row in reconcile(ROOT, tmp_path, ["codex"]))
    setup(tmp_path, ["codex"])
    another = rules.parent / "user.rules"
    another.write_text('prefix_rule(pattern=["git", ["commit", "status"]], decision="forbidden")\n')
    before = rules.read_bytes()
    assert any(row.startswith("CONFLICT codex") for row in reconcile(ROOT, tmp_path, ["codex"], apply=True))
    assert rules.read_bytes() == before


def test_owned_codex_forbidden_drift_is_repaired(tmp_path):
    setup(tmp_path, ["codex"])
    rules = tmp_path / ".codex/rules/default.rules"
    rules.write_text(rules.read_text().replace('decision="prompt"', 'decision="forbidden"'))
    reports = reconcile(ROOT, tmp_path, ["codex"])
    assert any(row.startswith("STALE codex") for row in reports)
    assert not any(row.startswith("CONFLICT") for row in reports)
    setup(tmp_path, ["codex"])
    assert rules.read_text() == (ROOT / "runtime/codex/default.rules").read_text()


@pytest.mark.parametrize("text", ['# BEGIN AI Engineering Harness\n',
                                 '# BEGIN AI Engineering Harness\n# END AI Engineering Harness\n' * 2,
                                 'load("unknown", "prefix_rule")\n'])
def test_ambiguous_markers_and_advanced_rules_refused(tmp_path, text):
    rules = tmp_path / ".codex/rules/default.rules"
    rules.parent.mkdir(parents=True)
    rules.write_text(text)
    assert any(row.startswith("CONFLICT") for row in reconcile(ROOT, tmp_path, ["codex"], apply=True))
    assert rules.read_text() == text


def test_symlink_configuration_refused(tmp_path):
    target = tmp_path / "personal.json"
    target.write_text("{}")
    settings = tmp_path / ".claude/settings.json"
    settings.parent.mkdir()
    settings.symlink_to(target)
    assert any(row.startswith("CONFLICT") for row in reconcile(ROOT, tmp_path, ["claude"], apply=True))
    assert settings.is_symlink() and target.read_text() == "{}"


def test_codex_allow_cannot_override_prompt(tmp_path):
    rules = tmp_path / ".codex/rules/default.rules"
    rules.parent.mkdir(parents=True)
    rules.write_text('prefix_rule(pattern=["git"], decision="allow")\n')
    setup(tmp_path, ["codex"])
    assert all(not row.startswith(("MISSING", "STALE", "CONFLICT")) for row in reconcile(ROOT, tmp_path, ["codex"]))


def test_codex_forbidden_read_does_not_conflict_with_commit_approval(tmp_path):
    rules = tmp_path / ".codex/rules/default.rules"
    rules.parent.mkdir(parents=True)
    rules.write_text('prefix_rule(pattern=["git", "-C", "/private", "status"], decision="forbidden")\n')
    setup(tmp_path, ["codex"])


def test_codex_override_is_not_silently_ignored(tmp_path):
    override = tmp_path / ".codex/AGENTS.override.md"
    override.parent.mkdir()
    override.write_text("Personal overriding adapter\n")
    reports = reconcile(ROOT, tmp_path, ["codex"], apply=True)
    assert any(row.startswith("CONFLICT codex") for row in reports)
    assert not (override.parent / "AGENTS.md").exists()


def test_runtime_paths_with_spaces_render_a_valid_hook(tmp_path):
    import shlex
    import shutil
    repo = tmp_path / "repo with spaces"
    shutil.copytree(ROOT / "runtime", repo / "runtime")
    hook = repo / "scripts/hooks/git_commit_guard.py"
    hook.parent.mkdir(parents=True)
    hook.write_text("# fixture\n")
    home = tmp_path / "home"
    reports = reconcile(repo, home, ["claude"], apply=True)
    assert not any(row.startswith("CONFLICT") for row in reports)
    settings = json.loads((home / ".claude/settings.json").read_text())
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert shlex.split(command)[1] == str(hook)


@pytest.mark.parametrize("command", [
    ["git", "commit", "-m", "fixture"], ["git", "-C", "/repo", "commit"],
    ["git", "-c", "alias.ci=commit", "ci"], ["git", "--git-dir", ".git", "commit"],
    ["git", "--work-tree", ".", "commit"], ["git", "--config-env", "alias.ci=ALIAS", "ci"],
    ["git", "--exec-path", "/helpers", "checkpoint"], ["/usr/bin/git", "commit"], ["/bin/git", "commit"],
])
def test_native_codex_rules_require_approval(command):
    import shutil
    if not shutil.which("codex"):
        pytest.skip("Codex native rules engine is not installed")
    result = subprocess.run(["codex", "execpolicy", "check", "--rules", str(ROOT / "runtime/codex/default.rules"), *command],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["decision"] == "prompt"


def test_real_home_provider_overrides_and_fake_home_isolation(tmp_path, monkeypatch):
    from runtime_guards import runtime_directory
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "custom-codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "custom-claude"))
    assert runtime_directory(Path.home(), "codex") == tmp_path / "custom-codex"
    assert runtime_directory(Path.home(), "claude") == tmp_path / "custom-claude"
    assert runtime_directory(tmp_path / "fake", "codex") == tmp_path / "fake/.codex"


def test_concurrent_config_change_refused(tmp_path):
    from runtime_guards import _write
    path = tmp_path / "settings.json"
    path.write_text("new user edit")
    with pytest.raises(OSError, match="configuration changed"):
        _write(path, "harness content", "previous content")
    assert path.read_text() == "new user edit"
