"""End-to-end runner behaviour against disposable git repos and the fake provider."""

import json
from pathlib import Path

import pytest

from autobuild.artifacts import RUN_ARTIFACTS
from autobuild.preflight import PreflightError, preflight
from autobuild.runner import Runner
from autobuild.schemas import schema_errors
from project_fixture import git, make_project


def _run(tmp_path, monkeypatch, mode="write", **project_kwargs):
    monkeypatch.setenv("FAKE_AGENT_MODE", mode)
    root, brief = make_project(tmp_path, **project_kwargs)
    main_before = git(root, "rev-parse", "main").strip()
    outcome = Runner(preflight(brief, root)).run()
    return root, outcome, main_before


def _states(outcome):
    return [h["state"] for h in outcome.state["history"]]


def test_successful_run_commits_on_run_branch_and_leaves_main(tmp_path, monkeypatch, fake_registry):
    root, outcome, main_before = _run(tmp_path, monkeypatch)
    state = outcome.state
    assert _states(outcome) == ["READY", "IMPLEMENTING", "VALIDATING", "REVIEWING", "PASSED", "COMPLETED"]
    assert state["branch"] == "agent/T-1-add-feature-file" and state["parent_branch"] == "main"
    assert state["review_mode"] == "independent" and state["base_commit"] == main_before
    worktree = Path(state["worktree"])
    assert worktree.parent == tmp_path / "proj.worktrees" and (worktree / "feature.txt").exists()
    # Checkpoint commit on the run branch only; main untouched.
    assert git(root, "rev-parse", "main").strip() == main_before
    assert git(root, "rev-parse", state["branch"]).strip() == state["last_commit"]
    assert git(root, "log", "-1", "--format=%s", state["branch"]).strip() == "autobuild(T-1): Add feature file"
    assert "feature.txt" in git(root, "show", "--name-only", "--format=", state["last_commit"])
    # Main checkout is unaffected; worktree status is clean after the commit.
    assert git(root, "status", "--porcelain") == "" and git(worktree, "status", "--porcelain") == ""


def test_run_artifacts_follow_contract(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch)
    run_dir = outcome.run_dir
    for spec in RUN_ARTIFACTS:
        if spec.path.startswith("browser/"):
            continue  # phase 0.4
        assert (run_dir / spec.path.replace("NN", "01").rstrip("/")).exists(), spec.path
    result = json.loads((run_dir / "implementation/result.json").read_text())
    assert schema_errors("implementation-result", result) == []
    assert result["report_status"] == "valid" and result["provider"] == "fake-a" and result["session_id"]
    validation = json.loads((run_dir / "validation/results.json").read_text())
    assert schema_errors("validation", validation) == [] and validation["producer"] == "controller"
    assert "feature.txt" in (run_dir / "implementation/diff.patch").read_text()
    assert (run_dir / "implementation/changed-files.txt").read_text().strip() == "A\tfeature.txt"
    assert "Implementation: T-1" in (run_dir / "report.md").read_text()
    assert "Add feature file" in (run_dir / "implementation/prompt.md").read_text()


def test_provider_configuration_switching_uses_same_flow(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, provider="fake-b")
    assert outcome.state["state"] == "COMPLETED"
    assert outcome.state["agent_sessions"][0]["provider"] == "fake-b"


def test_checkpoint_commits_disabled_leaves_work_uncommitted(tmp_path, monkeypatch, fake_registry):
    root, outcome, main_before = _run(tmp_path, monkeypatch, checkpoint=False)
    assert outcome.state["state"] == "COMPLETED" and outcome.state["last_commit"] is None
    assert outcome.state["checkpoint"]["reason"] == "git.checkpoint_commits is disabled in the project config"
    assert git(root, "rev-parse", outcome.state["branch"]).strip() == main_before
    assert "?? feature.txt" in git(Path(outcome.state["worktree"]), "status", "--porcelain")


def test_provider_failure_marks_failed_and_preserves_worktree(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, mode="fail")
    assert _states(outcome) == ["READY", "IMPLEMENTING", "FAILED"]
    assert outcome.state["failure"]["reason"] == "provider_failed"
    worktree = Path(outcome.state["worktree"])
    assert (worktree / "partial.txt").exists()  # partial work preserved
    assert "partial.txt" in (outcome.run_dir / "implementation/diff.patch").read_text()
    assert "simulated provider crash" in (outcome.run_dir / "logs/provider.stderr.log").read_text()


def test_validation_success_and_failure(tmp_path, monkeypatch, fake_registry):
    commands = [{"name": "always-fails", "kind": "test", "run": "echo nope >&2; exit 1"}]
    _, outcome, _ = _run(tmp_path, monkeypatch, commands=commands)
    assert _states(outcome) == ["READY", "IMPLEMENTING", "VALIDATING", "REVIEWING", "HUMAN_BLOCKED"]
    assert "reviewer cannot override" in outcome.state["human_gate"]["reason"]
    assert outcome.state["last_commit"] is None
    results = json.loads((outcome.run_dir / "validation/results.json").read_text())
    assert results["commands"][0]["status"] == "FAIL" and results["commands"][0]["exit_code"] == 1
    assert "nope" in (outcome.run_dir / results["commands"][0]["stderr_path"]).read_text()
    assert Path(outcome.state["worktree"], "feature.txt").exists()


def test_optional_and_path_filtered_commands(tmp_path, monkeypatch, fake_registry):
    commands = [
        {"name": "feature-exists", "kind": "test", "run": "test -f feature.txt"},
        {"name": "lint-optional", "kind": "lint", "run": "exit 1", "required": False},
        {"name": "web-only", "kind": "test", "run": "exit 1", "paths": ["web/*"]},
        {"name": "uses-vars", "kind": "other", "run": 'test "$WT" = "${WORKTREE}"', "env": {"WT": "${WORKTREE}"}},
    ]
    _, outcome, _ = _run(tmp_path, monkeypatch, commands=commands)
    statuses = {c["name"]: c["status"] for c in json.loads((outcome.run_dir / "validation/results.json").read_text())["commands"]}
    assert statuses == {"feature-exists": "PASS", "lint-optional": "FAIL", "web-only": "SKIPPED", "uses-vars": "PASS"}
    assert outcome.state["state"] == "COMPLETED"


def test_timeout_fails_run(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setenv("FAKE_AGENT_MODE", "sleep")
    root, brief = make_project(tmp_path)
    plan = preflight(brief, root)
    plan.implementer_timeout = 1
    outcome = Runner(plan).run()
    assert outcome.state["failure"]["reason"] == "provider_timeout"


def test_no_changes_fails(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, mode="noop")
    assert outcome.state["failure"]["reason"] == "no_changes"


def test_invalid_report_is_recorded_but_not_fatal(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, mode="bad_report")
    result = json.loads((outcome.run_dir / "implementation/result.json").read_text())
    assert result["report_status"] == "missing" and result["reported"] is None
    assert outcome.state["state"] == "COMPLETED"  # the evidence, not the report, decides


def test_agent_git_push_is_refused_by_guard(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, mode="git_push")
    code, message = Path(outcome.state["worktree"], "push-result.txt").read_text().split("\n", 1)
    assert code == "126" and "not allowed" in message


def test_agent_commit_bypassing_guard_fails_run(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, mode="agent_commit")
    assert outcome.state["failure"]["reason"] == "agent_committed"


def test_protected_branch_moved_by_agent_is_detected(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, mode="move_main")
    assert outcome.state["failure"]["reason"] == "protected_branch_modified"
    assert outcome.state["failure"]["recoverable"] is False


def test_secret_like_files_block_the_run(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch, mode="secret")
    assert outcome.state["failure"]["reason"] == "secret_like_files"
    assert outcome.state["last_commit"] is None


def test_browser_required_without_gates_stops_before_checkpoint(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setenv("FAKE_BROWSER_REVIEW", "1")
    root, outcome, main_before = _run(tmp_path, monkeypatch, browser=True)
    assert _states(outcome) == ["READY", "IMPLEMENTING", "VALIDATING", "REVIEWING", "HUMAN_BLOCKED"]
    assert "browser" in outcome.state["human_gate"]["reason"]
    # Required missing browser evidence now blocks checkpoints, including reviewer PASS.
    assert outcome.state["checkpoint"]["committed"] is False
    assert outcome.state["last_commit"] is None
    assert git(root, "rev-parse", "main").strip() == main_before


def test_checkpoint_decision_is_recorded(tmp_path, monkeypatch, fake_registry):
    _, outcome, _ = _run(tmp_path, monkeypatch)
    assert outcome.state["checkpoint"] == {"committed": True, "reason": "GREEN work validated on the isolated run branch"}
    assert "not pushed or merged" in (outcome.run_dir / "report.md").read_text()


def test_interrupt_stops_and_preserves(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setenv("FAKE_AGENT_MODE", "write")
    root, brief = make_project(tmp_path)
    plan = preflight(brief, root)

    def interrupted():
        raise KeyboardInterrupt
    monkeypatch.setattr(plan.adapter, "get_result", interrupted)
    outcome = Runner(plan).run()
    assert _states(outcome) == ["READY", "IMPLEMENTING", "STOP_REQUESTED", "STOPPED"]
    assert outcome.state["stop_requested"] is True and Path(outcome.state["worktree"]).is_dir()


def test_second_run_gets_distinct_branch_and_run_id(tmp_path, monkeypatch, fake_registry):
    root, outcome, _ = _run(tmp_path, monkeypatch)
    second = Runner(preflight(root / "docs/roadmap/T-1.md", root)).run()
    assert second.state["branch"] == "agent/T-1-add-feature-file-2"
    assert second.state["run_id"].endswith("-T-1-2") and second.state["state"] == "COMPLETED"


# --- Preflight refusals leave the repository untouched ---

def _assert_untouched(root: Path):
    assert git(root, "branch", "--format=%(refname:short)").split() == ["main"]
    assert git(root, "worktree", "list").count("\n") == 1
    assert not any(p.name != ".gitkeep" for p in (root / ".autobuild/runs").iterdir())


def test_missing_configured_provider_does_not_start(tmp_path, fake_registry):
    root, brief = make_project(tmp_path, provider="fake-missing")
    with pytest.raises(PreflightError) as exc:
        preflight(brief, root)
    assert "Configured implementer: fake-missing" in exc.value.issues
    assert any(i.startswith("Status: unavailable") for i in exc.value.issues)
    _assert_untouched(root)


def test_preflight_refuses_dirty_tree_bad_base_and_missing_test_command(tmp_path, fake_registry):
    root, brief = make_project(tmp_path, commands=[{"name": "lint", "kind": "lint", "run": "true"}])
    (root / "stray.txt").write_text("x")
    git(root, "branch", "feature/other")
    with pytest.raises(PreflightError) as exc:
        preflight(brief, root, base_branch="feature/other")
    joined = "\n".join(exc.value.issues)
    assert "uncommitted change" in joined
    assert "neither a protected branch nor an automation branch" in joined
    assert "defines no `test` command" in joined
    assert git(root, "branch", "--format=%(refname:short)").split() == ["feature/other", "main"]


def test_preflight_refuses_non_green_before_runtime_tool_resolution(tmp_path, fake_registry):
    root, brief = make_project(tmp_path, commands=[{"name": "t", "kind": "test", "run": "no-such-tool-xyz --run"}])
    brief.write_text(brief.read_text().replace("status: ready", "status: draft"))
    git(root, "commit", "-qam", "draft")
    with pytest.raises(PreflightError) as exc:
        preflight(brief, root)
    joined = "\n".join(exc.value.issues)
    assert "status is draft" in joined
    _assert_untouched(root)


def test_preflight_refuses_worktree_root_inside_project(tmp_path, fake_registry):
    root, brief = make_project(tmp_path, extra_git={"worktree_root": "inside"})
    with pytest.raises(PreflightError) as exc:
        preflight(brief, root)
    assert any("inside the project" in i for i in exc.value.issues)
