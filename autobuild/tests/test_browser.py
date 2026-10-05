"""Browser contracts, deterministic results, lifecycle, and review-loop integration."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from autobuild import browser_runner
from autobuild.browser_artifacts import collect
from autobuild.browser_contract import browser_config_errors, digest, evidence_errors, history_errors
from autobuild.browser_sandbox import isolated_environment, sandbox_command
from autobuild.cli import main
from autobuild.config import config_errors
from autobuild.preflight import PreflightError, preflight
from autobuild.resume import resume_preflight
from autobuild.runner import Runner
from project_fixture import git, make_project


@pytest.fixture
def local_worker(monkeypatch):
    # Benign unit fixtures only. Production has no unsandboxed execution mode.
    def command(worktree, inputs, writable, environment):
        worker = Path(browser_runner.__file__).with_name("browser_worker.py")
        return ["/usr/bin/env", *[f"{key}={value}" for key, value in environment.items()],
                sys.executable, str(worker), str(inputs / "request.json")]
    monkeypatch.setattr(browser_runner, "sandbox_command", command)


def gate(script="pass", **options):
    return {"id": "smoke", "kind": "e2e", "command": [sys.executable, "-c", script], **options}


def execute(tmp_path, specification, **options):
    worktree = tmp_path / "worktree"
    worktree.mkdir(exist_ok=True)
    run_dir = tmp_path / "run"
    document = browser_runner.run_browser(run_id="2026-10-04-T-1", attempt=options.pop("attempt", 1),
        review_cycle=options.pop("review_cycle", 1), worktree=worktree, head_commit="a" * 40,
        snapshot_tree="b" * 40, brief_sha256="c" * 64,
        config={"validation": {"browser_gates": [specification]}}, run_dir=run_dir, **options)
    return document, run_dir


@pytest.mark.parametrize("script,status,code", [("print('ok')", "PASS", 0), ("raise SystemExit(7)", "FAIL", 7),
    ("import time; time.sleep(4)", "ERROR", None)])
def test_results(tmp_path, local_worker, script, status, code):
    document, run = execute(tmp_path, gate(script, timeout_seconds=1))
    record = document["gates"][0]
    assert (record["status"], record["exit_code"]) == (status, code)
    assert document["passed"] == (status == "PASS")
    assert evidence_errors(run, "browser/cycle-01/results.json", digest(run / "browser/cycle-01/results.json")) == []


def test_missing_command(tmp_path, local_worker):
    document, _ = execute(tmp_path, gate(command=["/missing-browser-tool"]))
    assert document["gates"][0]["status"] == "ERROR"


def test_missing_sandbox_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr("autobuild.sandbox.shutil.which", lambda _: None)
    document, _ = execute(tmp_path, gate())
    assert document["gates"][0]["status"] == "ERROR"
    assert "requires bubblewrap" in document["gates"][0]["detail"]


def test_unsupported_platform_is_gate_error(tmp_path, monkeypatch):
    monkeypatch.setattr("autobuild.sandbox.sys.platform", "win32")
    document, _ = execute(tmp_path, gate())
    assert document["gates"][0]["status"] == "ERROR"
    assert "Linux Bubblewrap" in document["gates"][0]["detail"]


@pytest.mark.parametrize("enabled,required,passed", [(False, True, False), (False, False, True), (True, False, True)])
def test_optional_and_disabled_gates(tmp_path, local_worker, enabled, required, passed):
    document, _ = execute(tmp_path, gate("raise SystemExit(1)", enabled=enabled, required=required))
    assert document["passed"] == passed
    assert document["gates"][0]["status"] == ("FAIL" if enabled else "SKIPPED")


def test_outputs_and_tampering(tmp_path, local_worker):
    script = "import os; from pathlib import Path; Path(os.environ['AUTOBUILD_BROWSER_OUTPUT'], 'shot.png').write_bytes(b'image')"
    document, run = execute(tmp_path, gate(script, artifacts=["*.png"]))
    record = document["gates"][0]["artifacts"][0]
    assert (run / record["path"]).read_bytes() == b"image"
    artifact = "browser/cycle-01/results.json"
    fingerprint = digest(run / artifact)
    (run / record["path"]).write_bytes(b"changed")
    assert evidence_errors(run, artifact, fingerprint)


def test_missing_artifact_is_error(tmp_path, local_worker):
    document, _ = execute(tmp_path, gate(artifacts=["*.png"]))
    assert document["gates"][0]["status"] == "ERROR" and not document["passed"]


def test_root_symlink_cannot_collect_host_files(tmp_path):
    root = tmp_path / "outputs"
    root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        collect(root, tmp_path / "artifacts", ["**/*"], tmp_path)


def test_log_symlink_is_error(tmp_path, local_worker):
    script = "import os; from pathlib import Path; p=Path(os.environ['AUTOBUILD_BROWSER_OUTPUT']).parent/'stdout.txt'; p.unlink(); p.symlink_to('/etc/passwd')"
    document, run = execute(tmp_path, gate(script))
    assert document["gates"][0]["status"] == "ERROR"
    assert (run / document["gates"][0]["stdout_path"]).read_text() == ""


def test_output_contract_is_not_gate_truth(tmp_path, local_worker):
    script = "import os; from pathlib import Path; Path(os.environ['AUTOBUILD_BROWSER_OUTPUT'], 'report.json').write_text('{\\\"status\\\":\\\"PASS\\\"}'); raise SystemExit(2)"
    document, _ = execute(tmp_path, gate(script, artifacts=["report.json"]))
    assert document["gates"][0]["status"] == "FAIL"


def test_identity_mismatch_rejected(tmp_path, local_worker):
    document, run = execute(tmp_path, gate())
    state = {"run_id": "another-run", "worktree": document["worktree"], "brief_sha256": document["brief_sha256"],
             "browser_history": [{"attempt": 1, "review_cycle": 1, "snapshot_tree": document["snapshot_tree"],
             "passed": True, "artifact": "browser/cycle-01/results.json", "sha256": digest(run / "browser/cycle-01/results.json")}]}
    assert history_errors(run, state)


def test_cwd_symlink_escape_is_error(tmp_path, local_worker):
    (tmp_path / "worktree").mkdir()
    (tmp_path / "worktree/outside").symlink_to(tmp_path.parent, target_is_directory=True)
    document, _ = execute(tmp_path, gate(cwd="outside"))
    assert document["gates"][0]["status"] == "ERROR"


def test_interrupt_cleans_controller_subprocess(tmp_path, local_worker, monkeypatch):
    original = browser_runner.subprocess.Popen
    processes = []
    class Interrupted(original):
        def communicate(self, *args, **kwargs):
            processes.append(self)
            raise KeyboardInterrupt
    monkeypatch.setattr(browser_runner.subprocess, "Popen", Interrupted)
    with pytest.raises(KeyboardInterrupt):
        execute(tmp_path, gate("import time; time.sleep(30)"))
    assert processes[0].poll() is not None


def test_parent_watchdog_cleanup(tmp_path, local_worker, monkeypatch):
    original = browser_runner.subprocess.Popen
    processes = []
    class TimedOut(original):
        def communicate(self, *args, **kwargs):
            processes.append(self)
            raise subprocess.TimeoutExpired(self.args, 1)
    monkeypatch.setattr(browser_runner.subprocess, "Popen", TimedOut)
    document, _ = execute(tmp_path, gate("import time; time.sleep(30)"))
    assert document["gates"][0]["status"] == "ERROR"
    assert processes[0].poll() is not None


@pytest.mark.parametrize("result", ["{}", '{"status":"PASS","exit_code":9,"detail":"fake"}',
                                   '{"status":"FAIL","exit_code":0,"detail":"fake"}'])
def test_malformed_worker_is_error(tmp_path, monkeypatch, result):
    monkeypatch.setattr(browser_runner, "sandbox_command", lambda *args:
                        [sys.executable, "-c", "print(" + repr(result) + ")"])
    document, _ = execute(tmp_path, gate())
    assert document["gates"][0]["status"] == "ERROR"


def test_artifact_budget(tmp_path):
    for number in range(201):
        (tmp_path / f"artifact-{number}").touch()
    with pytest.raises(ValueError, match="exceeds"):
        collect(tmp_path, tmp_path / "collected", ["*"], tmp_path)


@pytest.mark.parametrize("attack", ["symlink", "directory-link", "hardlink", "fifo", "secret"])
def test_collection_rejects_unsafe_files(tmp_path, attack):
    source = tmp_path / "outputs"
    source.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("never collect")
    if attack == "symlink":
        (source / "shot").symlink_to(outside)
    elif attack == "directory-link":
        (source / "report").symlink_to(tmp_path, target_is_directory=True)
    elif attack == "hardlink":
        os.link(outside, source / "shot")
    elif attack == "fifo":
        os.mkfifo(source / "shot")
    else:
        (source / ".env").write_text("synthetic secret")
    with pytest.raises(ValueError):
        collect(source, tmp_path / "artifacts", ["**/*"], tmp_path)


@pytest.mark.parametrize("pattern", ["../outside", "/etc/passwd", "..\\outside"])
def test_traversal_rejected(tmp_path, pattern):
    with pytest.raises(ValueError):
        collect(tmp_path, tmp_path / "artifacts", [pattern], tmp_path)


@pytest.mark.parametrize("key", ["PATH", "HOME", "LD_PRELOAD", "AUTOBUILD_BROWSER_OUTPUT", "PYTHONPATH", "NODE_OPTIONS"])
def test_environment_override_rejected(key):
    assert browser_config_errors([gate(env={key: "bad"})])


@pytest.mark.parametrize("url", ["https://127.0.0.1:3000", "http://example.com:3000", "http://localhost", "http://user@localhost:3000"])
def test_readiness_url_rejected(url):
    assert browser_config_errors([gate(service={"command": ["true"], "ready_url": url})])


def test_schema_rejects_shell_string_duplicate_and_absolute(tmp_path, fake_registry):
    root, _ = make_project(tmp_path)
    import yaml
    config = yaml.safe_load((root / ".autobuild/config.yaml").read_text())
    for gates in ([gate(command="npm test")], [gate(), gate()], [gate(cwd="../other")], [gate(artifacts=["/etc/*"])]):
        config["validation"]["browser_gates"] = gates
        assert config_errors(config)


def test_environment_does_not_inherit_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_API_SECRET", "not-a-real-secret")
    environment = isolated_environment(tmp_path, {"PUBLIC_TEST": "yes"})
    assert "SYNTHETIC_API_SECRET" not in environment
    assert environment["PUBLIC_TEST"] == "yes"


def test_stdout_summary_bounded(tmp_path, local_worker):
    document, run = execute(tmp_path, gate("print('x' * 10000)"))
    record = document["gates"][0]
    assert len(record["stdout_summary"]) == 2048
    assert (run / record["stdout_path"]).stat().st_size == 10001


def test_fresh_attempt_never_overwrites(tmp_path, local_worker):
    first, run = execute(tmp_path, gate())
    before = (run / "browser/cycle-01/results.json").read_bytes()
    second, _ = execute(tmp_path, gate(), attempt=2, review_cycle=2)
    assert second["attempt"] == 2 and first["attempt"] == 1
    assert (run / "browser/cycle-01/results.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        execute(tmp_path, gate())


@pytest.mark.parametrize("script,status", [("pass", "PASS"), ("raise SystemExit(1)", "FAIL"),
                                          ("import time; time.sleep(5)", "ERROR")])
def test_service_cleanup(tmp_path, local_worker, script, status):
    try:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    except PermissionError:
        pytest.skip("loopback sockets unavailable in this execution environment")
    specification = gate(script, timeout_seconds=1, service={"command": [sys.executable, "-m", "http.server", str(port),
                        "--bind", "127.0.0.1"], "ready_url": f"http://127.0.0.1:{port}", "timeout_seconds": 2})
    document, _ = execute(tmp_path, specification)
    assert document["gates"][0]["status"] == status
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0


@pytest.mark.parametrize("command", [[sys.executable, "-c", "raise SystemExit(1)"],
                                   [sys.executable, "-c", "import time; time.sleep(10)"]])
def test_readiness_errors_cleanup(tmp_path, local_worker, command):
    document, _ = execute(tmp_path, gate(service={"command": command, "ready_url": "http://127.0.0.1:39127",
                                               "timeout_seconds": 1}))
    assert document["gates"][0]["status"] == "ERROR"


@pytest.mark.parametrize("script", ["raise SystemExit(1)", "pass"])
def test_reviewer_pass_cannot_override_required_failure(tmp_path, monkeypatch, local_worker, fake_registry, script):
    monkeypatch.setenv("FAKE_BROWSER_REVIEW", "1")
    root, brief = make_project(tmp_path, browser_gates=[gate(script)])
    before = git(root, "rev-parse", "main").strip()
    outcome = Runner(preflight(brief, root)).run()
    assert outcome.state["final_review_status"] == "PASS"
    assert outcome.state["state"] == ("COMPLETED" if script == "pass" else "HUMAN_BLOCKED")
    assert bool(outcome.state["last_commit"]) == (script == "pass")
    assert git(root, "rev-parse", "main").strip() == before


def revision_run(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_BROWSER_REVIEW", "1")
    monkeypatch.setenv("FAKE_REVIEW_SEQUENCE", "REVISE,PASS")
    script = "from pathlib import Path; raise SystemExit(0 if Path('feature.txt').read_text().endswith('1') else 1)"
    root, brief = make_project(tmp_path, browser=True, browser_gates=[gate(script)])
    return root, Runner(preflight(brief, root)).run()


def test_fail_revise_fix_pass_checkpoint(tmp_path, monkeypatch, local_worker, fake_registry, capsys):
    root, outcome = revision_run(tmp_path, monkeypatch)
    assert outcome.state["state"] == "COMPLETED", outcome.state.get("failure")
    history = outcome.state["browser_history"]
    assert [h["passed"] for h in history] == [False, True]
    assert len({h["snapshot_tree"] for h in history}) == 2
    assert len({h["sha256"] for h in history}) == 2
    assert outcome.state["checkpoint"]["committed"]
    prompt = (outcome.run_dir / "review/review-01-prompt.md").read_text()
    assert prompt.index("Controller Browser Evidence") < prompt.index("Supplemental Implementer Narrative")
    assert "browser/cycle-01/results.json" in (outcome.run_dir / "implementation/cycle-02/prompt.md").read_text()
    assert main(["evidence", str(outcome.run_dir), "--attempt", "1"]) == 0
    assert "smoke: FAIL" in capsys.readouterr().out


def test_reviewer_must_acknowledge_browser_evidence(tmp_path, fake_registry, local_worker):
    root, brief = make_project(tmp_path, browser_gates=[gate()])
    outcome = Runner(preflight(brief, root)).run()
    assert outcome.state["failure"]["reason"] == "invalid_review"


def test_resume_preserves_browser_history_and_reruns(tmp_path, monkeypatch, fake_registry, local_worker):
    monkeypatch.setenv("FAKE_BROWSER_REVIEW", "1")
    monkeypatch.setenv("FAKE_REVIEW_SEQUENCE", "BLOCK,PASS")
    root, brief = make_project(tmp_path, browser_gates=[gate()])
    first = Runner(preflight(brief, root)).run()
    before = (first.run_dir / "browser/cycle-01/results.json").read_bytes()
    second = Runner(resume_preflight(first.run_dir, root)).run()
    assert second.state["state"] == "COMPLETED"
    assert len(second.state["browser_history"]) == 2
    assert (first.run_dir / "browser/cycle-01/results.json").read_bytes() == before


def test_resume_rejects_browser_tampering(tmp_path, monkeypatch, fake_registry, local_worker):
    monkeypatch.setenv("FAKE_BROWSER_REVIEW", "1")
    monkeypatch.setenv("FAKE_REVIEW_SEQUENCE", "BLOCK")
    root, brief = make_project(tmp_path, browser_gates=[gate()])
    outcome = Runner(preflight(brief, root)).run()
    (outcome.run_dir / "browser/cycle-01/smoke/stdout.txt").write_text("tamper")
    with pytest.raises(PreflightError, match="browser artifact"):
        resume_preflight(outcome.run_dir, root)


def test_native_sandbox_readonly_refs_and_network(tmp_path):
    probe = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--unshare-user", "--unshare-net", "--", "/usr/bin/true"],
                           capture_output=True)
    if probe.returncode:
        pytest.skip("native user/network namespaces unavailable in this execution environment")
    script = """import os, socket
from pathlib import Path
try:
    Path('forbidden').write_text('escape')
except OSError:
    pass
else:
    raise SystemExit(3)
assert not Path.home().joinpath('.codex/auth.json').exists()
Path(os.environ['AUTOBUILD_BROWSER_OUTPUT'], 'proof.txt').write_text('confined')
"""
    document, _ = execute(tmp_path, gate(script, artifacts=["proof.txt"]))
    assert document["gates"][0]["status"] == "PASS", document["gates"][0]["detail"]
    assert not (tmp_path / "worktree/forbidden").exists()


def test_worker_cannot_be_shadowed_by_project(tmp_path, monkeypatch):
    monkeypatch.setattr("autobuild.sandbox.shutil.which", lambda name: "/usr/bin/bwrap" if name == "bwrap" else None)
    command = sandbox_command(tmp_path, tmp_path / "inputs", tmp_path / "outputs", {})
    worker = Path(browser_runner.__file__).with_name("browser_worker.py")
    assert command[-4:] == [sys.executable, "-I", str(worker), str(tmp_path / "inputs/request.json")]


def test_native_sandbox_service_and_protected_refs(tmp_path, fake_registry):
    probe = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--unshare-user", "--unshare-net", "--", "/usr/bin/true"],
                           capture_output=True)
    if probe.returncode:
        pytest.skip("native namespaces unavailable")
    root, brief = make_project(tmp_path)
    plan = preflight(brief, root)
    from autobuild.git_client import GitClient
    client = GitClient(root, ["main"])
    plan.worktree.parent.mkdir(parents=True)
    client.add_worktree(plan.worktree, plan.branch, plan.base_commit)
    before = git(root, "rev-parse", "main").strip()
    script = """import subprocess
from urllib.request import urlopen
from pathlib import Path
assert urlopen('http://127.0.0.1:38404').status == 200
assert subprocess.run(['/usr/bin/git', 'update-ref', 'refs/heads/main', 'HEAD'], capture_output=True).returncode != 0
try:
    Path('forbidden').write_text('escape')
except OSError:
    pass
else:
    raise SystemExit(3)
"""
    specification = gate(script, service={"command": [sys.executable, "-m", "http.server", "38404", "--bind", "127.0.0.1"],
                         "ready_url": "http://127.0.0.1:38404", "timeout_seconds": 3})
    document = browser_runner.run_browser(run_id=plan.run_id, attempt=1, review_cycle=1, worktree=plan.worktree,
        head_commit=plan.base_commit, snapshot_tree=git(root, "rev-parse", "HEAD^{tree}").strip(), brief_sha256="a" * 64,
        config={"validation": {"browser_gates": [specification]}}, run_dir=plan.run_dir)
    assert document["gates"][0]["status"] == "PASS", document["gates"][0]
    assert git(root, "rev-parse", "main").strip() == before
    assert not (plan.worktree / "forbidden").exists()
