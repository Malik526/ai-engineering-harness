"""Native and contract tests for fail-closed normal-validation confinement."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import pytest

from autobuild.config import config_errors
from autobuild.paths import CORE_ROOT
from autobuild.schemas import schema_errors
from autobuild.validation_contract import digest, evidence_errors, history_errors
from autobuild.validation_runner import run_validation
from project_fixture import git


@pytest.fixture
def confined(tmp_path, request):
    worktree = tmp_path / "source"
    worktree.mkdir()
    (worktree / "value.txt").write_text("host-original\n")
    (worktree / "pkg").mkdir()
    (worktree / "pkg" / "sample.py").write_text("VALUE = 1\n")
    git(worktree, "init", "-q", "-b", "main")
    git(worktree, "config", "user.name", "Test")
    git(worktree, "config", "user.email", "test@example.com")
    git(worktree, "add", "-A")
    git(worktree, "commit", "-q", "-m", "fixture")
    head = git(worktree, "rev-parse", "HEAD").strip()
    tree = git(worktree, "rev-parse", "HEAD^{tree}").strip()
    outcomes = []
    count = 0

    def execute(commands, *, config_validation=None):
        nonlocal count
        count += 1
        run_dir = tmp_path / f"run-{count}"
        run_dir.mkdir()
        validation = {"commands": commands, **(config_validation or {})}
        config = {"version": 1, "validation": validation}
        outcome = run_validation(
            run_id="2026-10-04-V-1", commands=commands, project_root=worktree,
            worktree=worktree, changed_files=["value.txt"], run_dir=run_dir,
            snapshot_tree=tree, head_commit=head, attempt=count, review_cycle=count,
            brief_sha256="a" * 64, config=config,
        )
        outcomes.append(outcome)
        return outcome, run_dir

    yield worktree, head, tree, execute
    for outcome in outcomes:
        outcome.cleanup()


def command(name, argv, **options):
    return {"name": name, "kind": options.pop("kind", "test"), "command": argv, **options}


def test_pass_fail_missing_executable_and_timeout(confined):
    _, _, _, execute = confined
    outcome, _ = execute([
        command("passes", ["test", "-f", "value.txt"]),
        command("fails", ["sh", "-c", "exit 7"]),
        command("missing", ["definitely-not-a-validation-tool"]),
        command("timeout", [sys.executable, "-c", "import time; time.sleep(3)"], timeout_seconds=1),
    ])
    records = {record["name"]: record for record in outcome.document["commands"]}
    assert (records["passes"]["status"], records["passes"]["exit_code"]) == ("PASS", 0)
    assert (records["fails"]["status"], records["fails"]["exit_code"]) == ("FAIL", 7)
    assert records["missing"]["status"] == "ERROR" and records["missing"]["exit_code"] is None
    assert records["timeout"]["status"] == "ERROR" and "TimeoutExpired" in records["timeout"]["detail"]
    assert outcome.failed_required == ("fails", "missing", "timeout")
    assert schema_errors("validation", outcome.document) == []


def test_bubblewrap_and_setup_failures_are_errors_without_host_fallback(confined, monkeypatch):
    worktree, _, _, execute = confined
    marker = worktree / "must-not-exist"
    spec = command("would-write-host", ["sh", "-c", f"printf escaped > {marker}"])
    monkeypatch.setattr("autobuild.sandbox.shutil.which", lambda _: None)
    missing, _ = execute([spec])
    assert missing.document["commands"][0]["status"] == "ERROR"
    assert "requires bubblewrap" in missing.document["commands"][0]["detail"]
    assert not marker.exists()

    def broken_policy(*_args, **_kwargs):
        raise RuntimeError("synthetic mount setup failure")

    monkeypatch.setattr("autobuild.validation_runner.sandbox_command", broken_policy)
    setup, _ = execute([spec])
    assert setup.document["commands"][0]["status"] == "ERROR"
    assert "mount setup failure" in setup.document["commands"][0]["detail"]
    assert not marker.exists()


def test_invalid_cwd_is_recorded_as_error(confined):
    _, _, _, execute = confined
    outcome, _ = execute([command("bad-cwd", ["true"], cwd="missing")])
    record = outcome.document["commands"][0]
    assert record["status"] == "ERROR" and "inside the source snapshot" in record["detail"]
    assert schema_errors("validation", outcome.document) == []


def test_malformed_network_policy_is_rejected_by_config():
    document = {
        "version": 1,
        "project": {"name": "x"},
        "agents": {role: {"provider": "codex"} for role in ("planner", "implementer", "reviewer")},
        "git": {"protected_branches": ["main"], "branch_prefix": "agent/"},
        "paths": {"roadmap": "docs", "project_state": "state.md", "adr_directory": "docs/decisions", "runs_directory": ".runs"},
        "limits": {"max_review_cycles": 1, "max_consecutive_implementations": 1},
        "validation": {"browser_tool": "none", "require_clean_git_before_start": True,
                       "commands": [command("bad-network", ["true"], network="ambient")]},
        "notifications": {"enabled": False, "provider": "console"},
        "control": {"remote_stop_enabled": False, "provider": "none"},
    }
    assert any("network" in error for error in config_errors(document))


def test_host_reads_writes_worktree_and_protected_refs_are_denied(confined, tmp_path):
    worktree, head, _, execute = confined
    host_secret = tmp_path / "outside-secret.txt"
    host_secret.write_text("not available in sandbox")
    outside_write = tmp_path / "outside-write.txt"
    script = """
set -eu
test ! -r "$HOST_SECRET"
! printf escaped > "$OUTSIDE_WRITE"
! printf changed > "$REAL_WORKTREE/value.txt"
! git -C "$REAL_WORKTREE" update-ref refs/heads/main HEAD
printf snapshot-write > value.txt
test "$(cat value.txt)" = snapshot-write
"""
    outcome, _ = execute([command("escape-attempts", ["sh", "-c", script], env={
        "HOST_SECRET": str(host_secret), "OUTSIDE_WRITE": str(outside_write), "REAL_WORKTREE": str(worktree),
    })])
    assert outcome.passed, outcome.document["commands"][0]["stderr_summary"]
    assert worktree.joinpath("value.txt").read_text() == "host-original\n"
    assert not outside_write.exists()
    assert git(worktree, "rev-parse", "main").strip() == head


def test_credential_directories_and_harness_metadata_are_invisible(confined):
    _, _, _, execute = confined
    # Only paths that exist on this host prove anything; each must vanish inside the sandbox.
    candidates = [Path.home() / name for name in (".ssh", ".aws", ".codex", ".claude", ".agents", ".config/gh",
                                                  ".gitconfig", ".bash_history")]
    candidates.append(CORE_ROOT.parent / ".git")
    present = [str(path) for path in candidates if path.exists()]
    assert present, "host has no credential-like paths to probe"
    script = 'for path in "$@"; do if test -e "$path"; then echo "visible: $path" >&2; exit 3; fi; done'
    outcome, _ = execute([command("credential-paths", ["sh", "-c", script, "probe", *present])])
    record = outcome.document["commands"][0]
    assert record["status"] == "PASS", record["stderr_summary"]


def test_missing_snapshot_never_falls_back_to_host(tmp_path):
    marker = tmp_path / "host-marker"
    spec = command("host-write", ["sh", "-c", f"printf escaped > {marker}"])
    with pytest.raises(ValueError, match="requires a controller source snapshot"):
        run_validation(run_id="2026-10-04-V-1", commands=[spec], project_root=tmp_path, worktree=tmp_path,
                       changed_files=[], run_dir=tmp_path / "run")
    with pytest.raises(ValueError, match="cannot claim"):
        run_validation(run_id="manual", commands=[spec], project_root=tmp_path, worktree=tmp_path,
                       changed_files=[], run_dir=tmp_path / "run", snapshot_tree="f" * 40, manual_host=True)
    assert not marker.exists()


def test_malformed_runtime_network_policy_is_error_without_execution(confined):
    worktree, _, _, execute = confined
    marker = worktree / "must-not-exist"
    outcome, _ = execute([command("bad-network", ["sh", "-c", f"printf escaped > {marker}"], network="ambient")])
    record = outcome.document["commands"][0]
    assert record["status"] == "ERROR" and "network policy" in record["detail"]
    assert outcome.failed_required == ("bad-network",) and not marker.exists()


def test_environment_is_filtered_and_values_are_absent_from_evidence(confined, monkeypatch):
    _, _, _, execute = confined
    secret = "super-secret-controller-value"
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", secret)
    outcome, _ = execute([command("environment", ["sh", "-c",
        'test -z "$AWS_SECRET_ACCESS_KEY" && test "$EXPLICIT_SETTING" = allowed'],
        env={"EXPLICIT_SETTING": "allowed"})])
    record = outcome.document["commands"][0]
    assert record["status"] == "PASS"
    assert "EXPLICIT_SETTING" in record["environment"]["keys"]
    assert "AWS_SECRET_ACCESS_KEY" not in record["environment"]["keys"]
    assert secret not in json.dumps(outcome.document)
    assert "allowed" not in json.dumps(record["environment"])


def test_reserved_environment_keys_are_rejected():
    from autobuild.validation_contract import validation_config_errors

    errors = validation_config_errors({"commands": [command("unsafe-env", ["true"], env={"PATH": "/tmp"})]})
    assert errors and "controller-owned or unsafe" in errors[0]


def test_writable_workspace_home_cache_temp_and_scratch(confined):
    _, _, _, execute = confined
    create = """
set -eu
mkdir -p build "$HOME/tool" "$XDG_CACHE_HOME/tool" "$AUTOBUILD_VALIDATION_SCRATCH/tool"
printf built > build/output.txt
printf home > "$HOME/tool/value"
printf cache > "$XDG_CACHE_HOME/tool/value"
printf scratch > "$AUTOBUILD_VALIDATION_SCRATCH/tool/value"
tmp=$(mktemp); printf temp > "$tmp"; test "$(cat "$tmp")" = temp
"""
    verify = "test \"$(cat build/output.txt)\" = built && test -f \"$HOME/tool/value\" && test -f \"$XDG_CACHE_HOME/tool/value\""
    outcome, _ = execute([
        command("build", ["sh", "-c", create], kind="build"),
        command("verify-build", ["sh", "-c", verify]),
    ])
    assert [record["status"] for record in outcome.document["commands"]] == ["PASS", "PASS"]


def test_minimal_root_is_read_only_outside_approved_paths(confined):
    _, _, _, execute = confined
    # Unmounted locations must reject writes outright, not absorb them into an ephemeral root.
    targets = [str(Path.home() / "autobuild-escape"), "/etc/autobuild-escape", "/opt-escape", "/run/escape",
               "/usr/autobuild-escape"]
    script = ('for target in "$@"; do if printf x > "$target" 2>/dev/null; then echo "wrote: $target" >&2; exit 3; fi; done; '
              'tmp=$(mktemp) && printf ok > "$tmp" && test "$(cat "$tmp")" = ok')
    outcome, _ = execute([command("read-only-root", ["sh", "-c", script, "probe", *targets])])
    record = outcome.document["commands"][0]
    assert record["status"] == "PASS", record["stderr_summary"]
    assert not (Path.home() / "autobuild-escape").exists()


def test_python_lint_and_node_compatibility(confined):
    _, _, _, execute = confined
    commands = [
        command("python-test", [sys.executable, "-c", "from pkg.sample import VALUE; assert VALUE == 1"]),
        command("python-lint", [sys.executable, "-m", "py_compile", "pkg/sample.py"], kind="lint"),
    ]
    if shutil.which("node"):
        commands.append(command("node-test", ["node", "-e", "require('assert').strictEqual(2 + 2, 4)"]))
    if shutil.which("npm"):
        commands.append(command("npm-runtime", ["npm", "--version"], kind="setup"))
    outcome, _ = execute(commands)
    assert outcome.passed
    assert all(record["status"] == "PASS" for record in outcome.document["commands"])


def _listener():
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen()
    return server, server.getsockname()[1]


def test_network_none_denies_and_explicit_host_is_visible(confined):
    _, _, _, execute = confined
    server, port = _listener()
    try:
        probe = "import socket,sys; s=socket.socket(); sys.exit(0 if s.connect_ex(('127.0.0.1', int(sys.argv[1]))) else 9)"
        denied, _ = execute([command("network-none", [sys.executable, "-c", probe, str(port)])])
        assert denied.document["commands"][0]["status"] == "PASS"
        assert denied.document["commands"][0]["network"] == "none"

        connect = "import socket,sys; socket.create_connection(('127.0.0.1', int(sys.argv[1])), 2).close()"
        allowed, _ = execute([command("network-host", [sys.executable, "-c", connect, str(port)], network="host")])
        assert allowed.document["commands"][0]["status"] == "PASS"
        assert allowed.document["commands"][0]["network"] == "host"
        server.settimeout(1)
        connection, _ = server.accept()
        connection.close()
    finally:
        server.close()


@pytest.mark.parametrize("exit_code", [0, 4])
def test_detached_children_do_not_survive_success_or_failure(confined, exit_code):
    _, _, _, execute = confined
    server, port = _listener()
    try:
        child = ("import socket,time; time.sleep(.4); "
                 f"socket.create_connection(('127.0.0.1', {port}), 1).close()")
        parent = ("import subprocess,sys; "
                  f"subprocess.Popen([sys.executable, '-c', {child!r}], start_new_session=True); "
                  f"raise SystemExit({exit_code})")
        outcome, _ = execute([command("child-cleanup", [sys.executable, "-c", parent], network="host")])
        expected = "PASS" if exit_code == 0 else "FAIL"
        assert outcome.document["commands"][0]["status"] == expected
        server.settimeout(.8)
        with pytest.raises(socket.timeout):
            server.accept()
    finally:
        server.close()


def test_detached_child_does_not_survive_timeout(confined):
    _, _, _, execute = confined
    server, port = _listener()
    try:
        child = ("import socket,time; time.sleep(1.5); "
                 f"socket.create_connection(('127.0.0.1', {port}), 1).close()")
        parent = ("import subprocess,sys,time; "
                  f"subprocess.Popen([sys.executable, '-c', {child!r}], start_new_session=True); time.sleep(30)")
        outcome, _ = execute([command("timeout-child", [sys.executable, "-c", parent], network="host",
                                      timeout_seconds=1)])
        record = outcome.document["commands"][0]
        assert record["status"] == "ERROR" and "TimeoutExpired" in record["detail"]
        server.settimeout(2)
        with pytest.raises(socket.timeout):
            server.accept()
    finally:
        server.close()


def test_evidence_hashes_source_binding_and_tamper_detection(confined):
    worktree, head, tree, execute = confined
    outcome, run_dir = execute([command("evidence", ["sh", "-c", "printf evidence"])])
    artifact = "validation/cycle-01/results.json"
    path = run_dir / artifact
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(outcome.document, indent=2) + "\n")
    fingerprint = digest(path)
    state = {
        "run_id": outcome.document["run_id"], "worktree": str(worktree), "brief_sha256": "a" * 64,
        "validation_history": [{"attempt": 1, "review_cycle": 1, "artifact": artifact,
                                "sha256": fingerprint, "snapshot_tree": tree, "passed": True}],
    }
    assert evidence_errors(run_dir, artifact, fingerprint) == []
    assert history_errors(run_dir, state) == []
    log = run_dir / outcome.document["commands"][0]["stdout_path"]
    log.write_text("tampered")
    assert evidence_errors(run_dir, artifact, fingerprint)
    assert git(worktree, "rev-parse", "HEAD").strip() == head


def test_source_identity_mismatch_is_rejected(confined):
    worktree, _, tree, execute = confined
    outcome, run_dir = execute([command("identity", ["true"])])
    artifact = "validation/cycle-01/results.json"
    path = run_dir / artifact
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(outcome.document))
    state = {
        "run_id": outcome.document["run_id"], "worktree": str(worktree), "brief_sha256": "a" * 64,
        "validation_history": [{"attempt": 1, "review_cycle": 1, "artifact": artifact,
                                "sha256": digest(path), "snapshot_tree": "f" * 40, "passed": True}],
    }
    assert tree != "f" * 40
    assert "identity" in " ".join(history_errors(run_dir, state))


def test_interruption_terminates_sandbox_and_cleans_workspace(confined, monkeypatch):
    worktree, _, _, execute = confined
    terminated = []

    class InterruptedProcess:
        pid = 987654

        def communicate(self, timeout):
            raise KeyboardInterrupt

        def poll(self):
            return None

    def materialize_without_process(_source, _tree, destination):
        shutil.copytree(worktree, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))

    monkeypatch.setattr("autobuild.validation_runner._materialize_snapshot", materialize_without_process)
    monkeypatch.setattr("autobuild.validation_runner.subprocess.Popen", lambda *_args, **_kwargs: InterruptedProcess())
    monkeypatch.setattr("autobuild.validation_runner.terminate_process_group", lambda process: terminated.append(process))
    with pytest.raises(KeyboardInterrupt):
        execute([command("interrupt", ["true"])])
    assert len(terminated) == 1
