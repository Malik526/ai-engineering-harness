"""Independent review, bounded correction, and human-initiated resume."""

import json
from pathlib import Path

import pytest
import yaml

from autobuild.preflight import PreflightError, preflight
from autobuild.resume import resume_preflight
from autobuild.runner import Runner
from autobuild.schemas import schema_errors
from project_fixture import git, make_project


def run_fixture(tmp_path, monkeypatch, sequence="PASS", **options):
    monkeypatch.setenv("FAKE_REVIEW_SEQUENCE", sequence)
    root, brief = make_project(tmp_path, **options)
    main = git(root, "rev-parse", "main").strip()
    outcome = Runner(preflight(brief, root)).run()
    assert git(root, "rev-parse", "main").strip() == main
    return root, outcome


@pytest.mark.parametrize("sequence,cycles", [("PASS", 1), ("REVISE,PASS", 2), ("REVISE,REVISE,PASS", 3)])
@pytest.mark.parametrize("reviewer", ["fake-a", "fake-b"])
def test_independent_review_and_revision(tmp_path, monkeypatch, fake_registry, sequence, cycles, reviewer):
    root, outcome = run_fixture(tmp_path, monkeypatch, sequence, reviewer=reviewer)
    state = outcome.state
    assert state["state"] == "COMPLETED", state.get("failure")
    assert state["final_review_status"] == "PASS" and state["review_cycle"] == cycles
    reviewers = [s for s in state["agent_sessions"] if s["role"] == "reviewer"]
    implementers = [s for s in state["agent_sessions"] if s["role"] == "implementer"]
    assert len(reviewers) == cycles and len(implementers) == cycles
    assert len({s["session_id"] for s in reviewers}) == cycles
    assert not {s["session_id"] for s in reviewers} & {s["session_id"] for s in implementers}
    assert len({s["session_id"] for s in implementers}) == 1
    assert all(s["provider"] == reviewer for s in reviewers)
    assert len(state["revision_history"]) == cycles and len(state["review_history"]) == cycles
    assert git(root, "rev-list", "--count", f"main..{state['branch']}").strip() == "1"
    trees = []
    for cycle in range(1, cycles + 1):
        directory = outcome.run_dir
        review = json.loads((directory / f"review/review-{cycle:02d}.json").read_text())
        assert schema_errors("review", review) == [] and review["reviewer"]["session_id"] == reviewers[cycle - 1]["session_id"]
        assert (directory / f"review/review-{cycle:02d}.md").exists()
        validation = json.loads((directory / f"validation/cycle-{cycle:02d}/results.json").read_text())
        assert validation["commands"][0]["status"] == "PASS"
        assert all(f"cycle-{cycle:02d}" in c["stdout_path"] for c in validation["commands"])
        trees.append(json.loads((directory / f"implementation/cycle-{cycle:02d}/git.json").read_text())["snapshot_tree"])
    assert len(set(trees)) == cycles
    first_prompt = (outcome.run_dir / "review/review-01-prompt.md").read_text()
    assert first_prompt.index("Actual Git Diff") < first_prompt.index("Supplemental Implementer Narrative")
    if cycles > 1:
        prompt = (outcome.run_dir / "implementation/cycle-02/prompt.md").read_text()
        assert "Required Review Findings" in prompt and "R1-1" in prompt


@pytest.mark.parametrize("sequence,reason", [("REVISE", "maximum review cycles"), ("BLOCK", "Human prerequisite"), ("BLOCKED", "Human prerequisite")])
def test_blocking_and_budget_preserve_work(tmp_path, monkeypatch, fake_registry, sequence, reason):
    root, outcome = run_fixture(tmp_path, monkeypatch, sequence, max_cycles=2)
    assert outcome.state["state"] == "HUMAN_BLOCKED"
    assert reason in outcome.state["human_gate"]["reason"]
    assert outcome.state["last_commit"] is None
    assert Path(outcome.state["worktree"], "feature.txt").exists()
    assert git(root, "rev-parse", outcome.state["branch"]).strip() == outcome.state["base_commit"]
    assert len(list((outcome.run_dir / "review").glob("review-*.json"))) >= 1


@pytest.mark.parametrize("sequence,reason", [("INVALID", "reviewer_failed"), ("FAIL", "reviewer_failed"), ("WRITE", "reviewer_modified_worktree")])
def test_unsafe_or_invalid_reviewer_fails(tmp_path, monkeypatch, fake_registry, sequence, reason):
    _, outcome = run_fixture(tmp_path, monkeypatch, sequence)
    assert outcome.state["state"] == "FAILED" and outcome.state["failure"]["reason"] == reason
    assert outcome.state["last_commit"] is None
    assert (outcome.run_dir / "logs/review-01/provider.log").exists()
    assert (outcome.run_dir / "review/review-01-result.json").exists()


def test_duplicate_reviewer_session_refused(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setenv("FAKE_REVIEW_SESSION", "reused")
    _, outcome = run_fixture(tmp_path, monkeypatch, "REVISE,PASS")
    assert outcome.state["failure"]["reason"] == "reviewer_session_reused"
    assert outcome.state["failure"]["recoverable"] is False


def test_validation_failure_is_reviewed_but_reviewer_cannot_override(tmp_path, monkeypatch, fake_registry):
    _, outcome = run_fixture(tmp_path, monkeypatch, commands=[{"name": "fails", "kind": "test", "run": "false"}])
    assert outcome.state["state"] == "HUMAN_BLOCKED"
    assert "reviewer cannot override" in outcome.state["human_gate"]["reason"]
    assert outcome.state["review_cycle"] == 1 and outcome.state["review_history"][0]["status"] == "PASS"
    assert outcome.state["last_commit"] is None


def test_revision_validation_failure_is_fresh_and_blocks_reviewer_pass(tmp_path, monkeypatch, fake_registry):
    _, outcome = run_fixture(tmp_path, monkeypatch, "REVISE,PASS", commands=[
        {"name": "initial-only", "kind": "test", "run": 'test "$(tail -c 1 feature.txt)" = 0'}])
    assert outcome.state["state"] == "HUMAN_BLOCKED"
    assert outcome.state["review_cycle"] == 2 and len(outcome.state["revision_history"]) == 2
    assert len(outcome.state["validation_history"]) == 2
    assert outcome.state["validation_history"][0]["passed"] is True
    assert outcome.state["validation_history"][1]["passed"] is False
    assert (outcome.run_dir / "review/review-02.json").exists()
    assert outcome.state["last_commit"] is None


def test_validation_content_mutation_is_discarded_with_snapshot(tmp_path, monkeypatch, fake_registry):
    root, outcome = run_fixture(tmp_path, monkeypatch, commands=[
        {"name": "mutates-copy", "kind": "test", "run": "printf mutation > feature.txt"},
        {"name": "sees-mutation", "kind": "test", "run": "test \"$(cat feature.txt)\" = mutation"},
    ])
    assert outcome.state["state"] == "COMPLETED"
    worktree = Path(outcome.state["worktree"])
    assert (worktree / "feature.txt").read_text() == "hello from the fake agent\n0"
    assert git(root, "show", f"{outcome.state['last_commit']}:feature.txt") == "hello from the fake agent\n0"


def test_missing_reviewer_refuses_without_creation(tmp_path, fake_registry):
    root, brief = make_project(tmp_path, reviewer="fake-missing")
    with pytest.raises(PreflightError, match="Configured reviewer: fake-missing"):
        preflight(brief, root)
    assert git(root, "branch", "--format=%(refname:short)").split() == ["main"]
    assert len(list((root / ".autobuild/runs").iterdir())) == 1


def test_resume_human_block_preserves_history_and_sessions(tmp_path, monkeypatch, fake_registry):
    root, outcome = run_fixture(tmp_path, monkeypatch, "BLOCK,PASS")
    first_review = (outcome.run_dir / "review/review-01.json").read_bytes()
    resumed = Runner(resume_preflight(outcome.run_dir, root)).run()
    assert resumed.state["state"] == "COMPLETED", resumed.state.get("failure")
    assert resumed.state["run_id"] == outcome.state["run_id"]
    assert resumed.state["worktree"] == outcome.state["worktree"]
    assert resumed.state["history"][:len(outcome.state["history"])] == outcome.state["history"]
    assert resumed.state["revision_history"][1]["resume_session_id"] == outcome.state["agent_sessions"][0]["session_id"]
    assert (outcome.run_dir / "review/review-01.json").read_bytes() == first_review
    assert resumed.state["review_cycle"] == 2


def test_recoverable_failure_resume(tmp_path, monkeypatch, fake_registry):
    monkeypatch.setenv("FAKE_AGENT_MODE", "fail")
    root, outcome = run_fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_AGENT_MODE", "write")
    resumed = Runner(resume_preflight(Path(outcome.state["run_id"]), root)).run()
    assert resumed.state["state"] == "COMPLETED"
    assert Path(resumed.state["worktree"], "partial.txt").exists()


@pytest.mark.parametrize("tamper", ["brief", "config", "branch", "main", "secret", "lock", "artifact", "attempts"])
def test_resume_tampering_refused(tmp_path, monkeypatch, fake_registry, tamper):
    root, outcome = run_fixture(tmp_path, monkeypatch, "BLOCK")
    if tamper == "brief":
        (outcome.run_dir / "brief.md").write_text("tampered")
    elif tamper == "config":
        path = root / ".autobuild/config.yaml"
        path.write_text(path.read_text().replace("checkpoint_commits: true", "checkpoint_commits: false"))
    elif tamper == "branch":
        git(Path(outcome.state["worktree"]), "checkout", "-b", "wrong")
    elif tamper == "main":
        git(root, "commit", "--allow-empty", "-m", "human changed main")
    elif tamper == "secret":
        Path(outcome.state["worktree"], ".env").write_text("not a real secret")
    elif tamper == "lock":
        (outcome.run_dir / ".controller.lock").touch()
    elif tamper == "attempts":
        path = outcome.run_dir / "state.json"
        state = json.loads(path.read_text())
        state["revision_history"] = []
        path.write_text(json.dumps(state))
    else:
        (outcome.run_dir / "review/review-01.json").unlink()
    with pytest.raises(PreflightError):
        resume_preflight(outcome.run_dir, root)


def test_resume_budget_requires_human_increase(tmp_path, monkeypatch, fake_registry):
    root, outcome = run_fixture(tmp_path, monkeypatch, "REVISE,PASS", max_cycles=1)
    with pytest.raises(PreflightError, match="budget exhausted"):
        resume_preflight(outcome.run_dir, root)
    path = root / ".autobuild/config.yaml"
    config = yaml.safe_load(path.read_text())
    config["limits"]["max_review_cycles"] = 2
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(PreflightError, match="--override-limits"):
        resume_preflight(outcome.run_dir, root)  # a raised limit is never applied implicitly
    resumed = Runner(resume_preflight(outcome.run_dir, root, override_limits=True)).run()
    assert resumed.state["state"] == "COMPLETED"
    [override] = resumed.state["governance"]["overrides"]
    assert override["changes"] == [{"key": "limits.max_review_cycles", "from": 1, "to": 2}]


def test_resume_rejects_review_linked_to_stale_validation(tmp_path, monkeypatch, fake_registry):
    root, outcome = run_fixture(tmp_path, monkeypatch, "REVISE,BLOCK")
    path = outcome.run_dir / "state.json"
    state = json.loads(path.read_text())
    state["review_history"][1]["validation_artifact"] = state["review_history"][0]["validation_artifact"]
    path.write_text(json.dumps(state))
    with pytest.raises(PreflightError, match="cycle/source"):
        resume_preflight(outcome.run_dir, root)


def test_completed_and_nonrecoverable_runs_cannot_resume(tmp_path, monkeypatch, fake_registry):
    root, outcome = run_fixture(tmp_path, monkeypatch)
    with pytest.raises(PreflightError, match="only STOPPED"):
        resume_preflight(outcome.run_dir, root)


def test_nonrecoverable_failure_refuses_resume(tmp_path, monkeypatch, fake_registry):
    root, outcome = run_fixture(tmp_path, monkeypatch, "WRITE")
    with pytest.raises(PreflightError, match="not recoverable"):
        resume_preflight(outcome.run_dir, root)


def test_failed_review_at_budget_limit_human_blocks(tmp_path, monkeypatch, fake_registry):
    _, outcome = run_fixture(tmp_path, monkeypatch, "REVISE,INVALID", max_cycles=2)
    assert outcome.state["state"] == "HUMAN_BLOCKED"
    assert "maximum review cycles" in outcome.state["human_gate"]["reason"]
    assert outcome.state["last_commit"] is None


def test_reviewer_cannot_reuse_implementer_identity(tmp_path, monkeypatch, fake_registry):
    from fake_provider import FakeAdapter
    original = FakeAdapter.parse_output
    identities = []

    def parse(adapter, request, stdout):
        session, report, error = original(adapter, request, stdout)
        if request.role == "implementer":
            identities.append(session)
        else:
            session = identities[0]
        return session, report, error

    monkeypatch.setattr(FakeAdapter, "parse_output", parse)
    _, outcome = run_fixture(tmp_path, monkeypatch)
    assert outcome.state["failure"]["reason"] == "reviewer_session_reused"


def test_resume_provider_must_retain_session_identity(tmp_path, monkeypatch, fake_registry):
    from fake_provider import FakeAdapter
    original = FakeAdapter.parse_output

    def parse(adapter, request, stdout):
        session, report, error = original(adapter, request, stdout)
        if request.resume_session_id:
            session = "unexpected-new-session"
        return session, report, error

    monkeypatch.setattr(FakeAdapter, "parse_output", parse)
    _, outcome = run_fixture(tmp_path, monkeypatch, "REVISE,PASS")
    assert outcome.state["failure"]["reason"] == "implementer_resume_mismatch"


def test_stopped_run_explicit_resume(tmp_path, monkeypatch, fake_registry):
    root, brief = make_project(tmp_path)
    plan = preflight(brief, root)
    monkeypatch.setattr(plan.adapter, "get_result", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    stopped = Runner(plan).run()
    assert stopped.state["state"] == "STOPPED"
    resumed = Runner(resume_preflight(stopped.run_dir, root)).run()
    assert resumed.state["state"] == "COMPLETED"
    assert resumed.state["revision_history"][1]["resume_session_id"] == stopped.state["agent_sessions"][0]["session_id"]
