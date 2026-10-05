"""Provider-neutral, bounded independent review loop. All work is preserved."""

import os
import json
import hashlib
import copy
import shutil
import sys
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from autobuild.agent_provider import AgentRequest, AgentResult
from autobuild.checkpoint_policy import decide_checkpoint
from autobuild.git_client import GitClient
from autobuild.git_evidence import GitEvidence, capture
from autobuild.git_shim import write_shim
from autobuild.paths import CORE_ROOT
from autobuild.preflight import RunPlan
from autobuild.prompt_builder import build_prompt
from autobuild.roles import IMPLEMENTER, REVIEWER
from autobuild.provider_loader import load_adapter
from autobuild.review_prompt import review_prompt, revision_prompt
from autobuild.run_report import format_report
from autobuild.run_store import RunStore, close_logger, utc_now
from autobuild.safety import is_protected_branch
from autobuild.schemas import load_schema, schema_errors
from autobuild.states import RunState
from autobuild.validation_runner import ValidationOutcome, command_argv, run_validation

from autobuild.secret_files import secret_like
from autobuild.browser_contract import digest, history_errors
from autobuild.browser_runner import run_browser
from autobuild.validation_contract import digest as validation_digest, history_errors as validation_history_errors


class RunAborted(Exception):
    """Stop the run at the current step; the state has already been recorded."""


@dataclass
class RunOutcome:
    state: dict[str, Any]
    run_dir: Path
    report: str


class Runner:
    def __init__(self, plan: RunPlan):
        self.plan = plan
        self.git = GitClient(plan.project_root, plan.config.protected_branches)
        self.store: Optional[RunStore] = None
        self.result: Optional[AgentResult] = None
        self.evidence: Optional[GitEvidence] = None
        self.validation: Optional[ValidationOutcome] = None
        self.protected_before: dict[str, Optional[str]] = {}
        self.attempt = 0
        self.active_adapter = plan.adapter
        self.expected_head = plan.base_commit
        self.browser = None

    # --- Entry point ---

    def run(self) -> RunOutcome:
        plan = self.plan
        lock = plan.run_dir / ".controller.lock"
        plan.run_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            return self._run_locked()
        finally:
            if self.validation is not None:
                self.validation.cleanup()
            close_logger(self.store)
            lock.unlink(missing_ok=True)

    def _run_locked(self) -> RunOutcome:
        plan = self.plan
        try:
            if plan.resume_state:
                persisted = json.loads((plan.run_dir / "state.json").read_text())
                if persisted != plan.resume_state:
                    raise RuntimeError("run state changed after resume preflight")
                self.store = RunStore(plan.run_dir, plan.config, persisted)
                self.protected_before = persisted["protected_refs"]
                self.expected_head = persisted["last_commit"] or plan.base_commit
                self.attempt = len(persisted.get("revision_history", []))
                self.store.transition(RunState.READY, by_human=True, failure=None, human_gate=None,
                                      stop_requested=False, final_review_status=None)
            else:
                self.store = RunStore.create(config=plan.config, run_dir=plan.run_dir, run_id=plan.run_id,
                                            implementation_id=plan.meta["id"], brief_path=plan.brief_path,
                                            review_mode="independent")
                self.store.update(review_history=[], revision_history=[], validation_history=[], browser_history=[], final_review_status=None)
                self._create_worktree()
            self._implement(resume=bool(plan.resume_state))
            self._collect_evidence()
            self._validate()
            self._browser()
            while True:
                review = self._review()
                if review["status"] == "PASS":
                    if self.validation is None or not self.validation.passed:
                        self._human_block("required normal validation did not PASS; reviewer cannot override controller evidence")
                        raise RunAborted
                    if self.browser is not None and not self.browser["passed"]:
                        self._human_block("required browser gates did not PASS; reviewer cannot override controller evidence")
                        raise RunAborted
                    self.store.transition(RunState.PASSED)
                    break
                if review["status"] == "BLOCK":
                    self._human_block(review["blocked_reason"])
                    raise RunAborted
                if self.store.state["review_cycle"] >= plan.config.data["limits"]["max_review_cycles"]:
                    self._human_block("maximum review cycles reached without PASS")
                    raise RunAborted
                self.store.transition(RunState.REVISING)
                self._implement(resume=True, review=review)
                self._collect_evidence()
                self._validate()
                self._browser()
            self._finish()
        except RunAborted:
            pass
        except KeyboardInterrupt:
            self._stop()
        except Exception as exc:  # noqa: BLE001 — every failure must end in a recorded state
            self.active_adapter.terminate()
            if self.store is None:
                raise
            self.store.log.error("unexpected error:\n%s", traceback.format_exc())
            if self.store.current not in (RunState.FAILED, RunState.STOPPED, RunState.COMPLETED, RunState.HUMAN_BLOCKED):
                self.store.fail("controller_error", f"{type(exc).__name__}: {exc}")
        report = format_report(self.store.state, self._result_doc(), self.evidence, self.validation, plan)
        self.store.write_text("report.md", report)
        return RunOutcome(state=self.store.state, run_dir=plan.run_dir, report=report)

    # --- Steps ---

    def _create_worktree(self) -> None:
        plan, store = self.plan, self.store
        plan.worktree.parent.mkdir(parents=True, exist_ok=True)
        self.git.add_worktree(plan.worktree, plan.branch, plan.base_commit)
        store.update(branch=plan.branch, parent_branch=plan.base_branch, worktree=str(plan.worktree),
                     base_commit=plan.base_commit)
        store.log.info("worktree %s on %s from %s@%s", plan.worktree, plan.branch, plan.base_branch, plan.base_commit[:12])
        # Guard: the worktree must exist, sit on the run branch, at the recorded base commit.
        problems = []
        if not plan.worktree.is_dir():
            problems.append("worktree directory missing")
        if self.git.current_branch(plan.worktree) != plan.branch:
            problems.append(f"worktree is not on {plan.branch}")
        if self.git.read("rev-parse", "HEAD", cwd=plan.worktree).strip() != plan.base_commit:
            problems.append("worktree HEAD does not match the recorded base commit")
        if problems:
            self._abort("worktree_mismatch", "; ".join(problems))
        self.protected_before = self.git.protected_refs()
        store.update(protected_refs=self.protected_before)

    def _implement(self, *, resume: bool = False, review: Optional[dict] = None) -> None:
        plan, store = self.plan, self.store
        self._verify_frozen_brief()
        self._verify_browser_history()
        self._verify_validation_history()
        self._verify_protected_refs()
        if self.git.current_branch(plan.worktree) != plan.branch or self.git.read(
                "rev-parse", "HEAD", cwd=plan.worktree).strip() != self.expected_head:
            self._abort("worktree_mismatch", "branch or HEAD changed before implementer launch", recoverable=False)
        project_docs = [plan.config.data["paths"][k] for k in ("project_state", "adr_directory", "roadmap")]
        commands = [{**c, "display": command_argv(c, plan.worktree, plan.worktree)[0]} for c in plan.validation_commands]
        prompt = build_prompt(brief_text=(store.path("brief.md")).read_text(), worktree=plan.worktree,
                              branch=plan.branch, base_branch=plan.base_branch, base_commit=plan.base_commit,
                              project_docs=project_docs, validation_commands=commands)
        previous = [s for s in store.state["agent_sessions"] if s["role"] == IMPLEMENTER]
        resumed_id = previous[-1]["session_id"] if resume and previous else None
        if resume:
            if review is None and store.state.get("review_history"):
                review = json.loads(store.path(store.state["review_history"][-1]["artifact"]).read_text())
            prompt = revision_prompt(plan, store, review)
        self.attempt += 1
        prefix = f"implementation/cycle-{self.attempt:02d}"
        prompt_file = store.write_text(f"{prefix}/prompt.md", prompt)
        store.write_text("implementation/prompt.md", prompt)

        real_git = shutil.which("git")
        guard_bin = store.path("guard/bin")
        write_shim(guard_bin, sys.executable, CORE_ROOT)
        session_id = resumed_id or str(uuid.uuid4())
        request = AgentRequest(
            role=IMPLEMENTER, prompt_file=prompt_file, working_directory=plan.worktree,
            output_directory=store.path(f"logs/implementation-{self.attempt:02d}"), report_schema=load_schema("implementation-report"),
            session_id=session_id, timeout_seconds=plan.implementer_timeout, model=plan.assignment.model,
            resume_session_id=resumed_id,
            env={"PATH": f"{guard_bin}{os.pathsep}{os.environ.get('PATH', '')}", "AUTOBUILD_REAL_GIT": real_git or "git",
                 "AUTOBUILD_WORKTREE": str(plan.worktree), "AUTOBUILD_RUN_ID": plan.run_id,
                 "AUTOBUILD_ROLE": IMPLEMENTER, "AUTOBUILD_IMPLEMENTATION_ID": plan.meta["id"],
                 "AUTOBUILD_REVIEW_CYCLE": str(store.state["review_cycle"]),
                 "AUTOBUILD_SESSION_ID": resumed_id or session_id},
        )
        session = {"provider": plan.assignment.provider, "role": IMPLEMENTER, "session_id": session_id,
                   "started_at": utc_now(), "ended_at": None}
        sessions = store.state["agent_sessions"] + [session]
        history = store.state["revision_history"] + [{"attempt": self.attempt, "cycle": store.state["review_cycle"],
                   "session_id": session_id, "resume_session_id": resumed_id, "artifact_directory": prefix,
                   "started_at": session["started_at"], "ended_at": None}]
        fields = {"agent_sessions": sessions, "revision_history": history}
        if store.current == RunState.REVISING:
            store.update(**fields)
        else:
            store.transition(RunState.IMPLEMENTING, **fields)
        store.log.info("invoking implementer %s (%s)", plan.assignment.provider, plan.assignment.command)
        self.active_adapter = plan.adapter
        plan.adapter.start(request)
        try:
            self.result = plan.adapter.get_result()
        except KeyboardInterrupt:
            plan.adapter.terminate()
            raise
        session.update(session_id=self.result.session_id or session_id, ended_at=utc_now())
        history[-1].update(session_id=session["session_id"], ended_at=session["ended_at"])
        store.update(agent_sessions=sessions, revision_history=history)
        store.write_json("implementation/result.json", self._result_doc())
        store.write_text("implementation/summary.md", _summary_markdown(self._result_doc()))
        for filename in ("result.json", "summary.md"):
            shutil.copyfile(store.path(f"implementation/{filename}"), store.path(f"{prefix}/{filename}"))
        for filename in ("provider.log", "provider.stderr.log"):
            source = request.output_directory / filename
            if source.exists():
                shutil.copyfile(source, store.path(f"logs/{filename}"))
        store.log.info("implementer ended: exit=%s timed_out=%s report=%s", self.result.exit_code,
                       self.result.timed_out, "valid" if self.result.structured_output else self.result.output_error)
        self._verify_protected_refs()
        if resumed_id and self.result.session_id != resumed_id:
            self._abort("implementer_resume_mismatch", "provider did not resume the recorded implementer session", recoverable=False)

    def _collect_evidence(self) -> None:
        plan = self.plan
        self._verify_frozen_brief()
        self.evidence = capture(self.git, plan.worktree, plan.run_dir, plan.base_commit)
        for filename in ("git.json", "changed-files.txt", "diff.patch"):
            shutil.copyfile(self.store.path(f"implementation/{filename}"),
                            self.store.path(f"implementation/cycle-{self.attempt:02d}/{filename}"))
        result = self.result
        if result is not None and not result.succeeded:
            reason = "provider_timeout" if result.timed_out else "provider_failed"
            self._abort(reason, f"configured implementer {plan.assignment.provider}: exit_code={result.exit_code} "
                               f"timed_out={result.timed_out}; {result.output_error or 'see logs/provider*.log'}")
        if self.evidence.branch != plan.branch:
            self._abort("branch_changed", f"worktree moved off {plan.branch} (now {self.evidence.branch})")
        if self.evidence.head_commit != self.expected_head:
            self._abort("agent_committed", "the implementer created commits; only the controller may commit")
        if not self.evidence.has_changes:
            self._abort("no_changes", "the implementer made no changes")
        secrets = secret_like(self.evidence.changed_paths)
        if secrets:
            self._abort("secret_like_files", "changes include files that look like secrets: " + ", ".join(secrets), recoverable=False)

    def _validate(self) -> None:
        plan, store = self.plan, self.store
        store.transition(RunState.VALIDATING)
        self.validation = run_validation(run_id=plan.run_id, commands=plan.validation_commands,
                                         project_root=plan.project_root, worktree=plan.worktree,
                                         changed_files=self.evidence.changed_paths, run_dir=plan.run_dir,
                                         logs_subdirectory=f"validation/cycle-{self.attempt:02d}/logs",
                                         snapshot_tree=self.evidence.snapshot_tree, head_commit=self.evidence.head_commit,
                                         attempt=self.attempt, review_cycle=store.state["review_cycle"] + 1,
                                         brief_sha256=store.state["brief_sha256"], config=plan.config.data)
        errors = schema_errors("validation", self.validation.document)
        if errors:
            raise RuntimeError("validation results violate schema: " + "; ".join(errors))
        store.write_json("validation/results.json", self.validation.document)
        store.write_json(f"validation/cycle-{self.attempt:02d}/results.json", self.validation.document)
        artifact = f"validation/cycle-{self.attempt:02d}/results.json"
        history = store.state.get("validation_history", []) + [{
            "attempt": self.attempt, "review_cycle": self.validation.document["review_cycle"], "artifact": artifact,
            "sha256": validation_digest(store.path(artifact)), "snapshot_tree": self.evidence.snapshot_tree,
            "passed": self.validation.passed,
        }]
        store.update(validation_history=history)
        self._verify_snapshot("validation")

    def _review(self) -> dict:
        plan, store = self.plan, self.store
        self._verify_browser_history()
        self._verify_validation_history()
        cycle = store.state["review_cycle"] + 1
        if cycle > plan.config.data["limits"]["max_review_cycles"]:
            self._human_block("maximum review cycles reached without PASS")
            raise RunAborted
        assignment = plan.reviewer_assignment or plan.config.agents[REVIEWER]
        plan.reviewer_assignment = assignment
        session_id = str(uuid.uuid4())
        prefix = f"review/review-{cycle:02d}"
        prompt_file = store.write_text(f"{prefix}-prompt.md", review_prompt(plan, store, cycle, self.attempt, session_id))
        session = {"provider": assignment.provider, "role": REVIEWER, "session_id": session_id,
                   "started_at": utc_now(), "ended_at": None}
        sessions = store.state["agent_sessions"] + [session]
        store.transition(RunState.REVIEWING, review_cycle=cycle, agent_sessions=sessions)
        adapter = load_adapter(assignment)
        self.active_adapter = adapter
        health = adapter.health_check()
        if not health.available:
            self._abort("reviewer_unavailable", f"configured reviewer {assignment.provider}: {health.detail}")
        request = AgentRequest(role=REVIEWER, prompt_file=prompt_file, working_directory=plan.worktree,
                               output_directory=store.path(f"logs/review-{cycle:02d}"), report_schema=load_schema("review"),
                               session_id=session_id, timeout_seconds=plan.reviewer_timeout, model=assignment.model,
                               env={"AUTOBUILD_ROLE": REVIEWER, "AUTOBUILD_RUN_ID": plan.run_id,
                                    "AUTOBUILD_WORKTREE": str(plan.worktree), "AUTOBUILD_IMPLEMENTATION_ID": plan.meta["id"],
                                    "AUTOBUILD_REVIEW_CYCLE": str(cycle), "AUTOBUILD_SESSION_ID": session_id,
                                    "AUTOBUILD_REAL_GIT": shutil.which("git") or "git",
                                    "PATH": f"{store.path('guard/bin')}{os.pathsep}{os.environ.get('PATH', '')}"})
        adapter.start(request)
        result = adapter.get_result()
        actual_id = result.session_id or session_id
        store.write_json(f"{prefix}-result.json", {"provider": result.provider, "session_id": actual_id,
                         "exit_code": result.exit_code, "timed_out": result.timed_out,
                         "error": result.output_error, "report": result.structured_output})
        if any(s["session_id"] == actual_id for s in sessions[:-1]):
            self._abort("reviewer_session_reused", "reviewer reused an existing session", recoverable=False)
        session.update(session_id=actual_id, ended_at=utc_now())
        store.update(agent_sessions=sessions)
        self._verify_snapshot("reviewer")
        self._verify_browser_history()
        self._verify_validation_history()
        if not result.succeeded or result.structured_output is None:
            self._abort("reviewer_failed", f"configured reviewer {assignment.provider}: exit={result.exit_code}; {result.output_error}")
        review = dict(result.structured_output)
        errors = schema_errors("review", review)
        if errors:
            self._abort("invalid_review", "; ".join(errors))
        if (review.get("run_id"), review.get("implementation_id"), review.get("cycle")) != (plan.run_id, plan.meta["id"], cycle):
            errors.append("review identity does not match the current run/cycle")
        if not {"brief", "git_diff", "changed_files", "validation_output"} <= set(review.get("evidence_reviewed", [])):
            errors.append("required authoritative evidence is missing")
        if self.browser is not None and "browser_evidence" not in review.get("evidence_reviewed", []):
            errors.append("controller browser evidence was not reviewed")
        findings = review.get("findings", [])
        if len({f["id"] for f in findings}) != len(findings):
            errors.append("finding IDs are not unique")
        if errors:
            self._abort("invalid_review", "; ".join(errors))
        review.update(reviewer={"provider": assignment.provider, "session_id": actual_id}, reviewed_at=utc_now())
        if review["status"] == "BLOCKED":
            review["status"] = "BLOCK"
        store.write_json(f"{prefix}.json", review)
        lines = [f"# Review {cycle}: {review['status']}", "", review.get("blocked_reason", "")]
        for finding in findings:
            lines += [f"## {finding['id']} ({finding['severity']})", finding["requirement"], finding["evidence"],
                      ", ".join(finding["affected_files"]), finding["required_correction"], ""]
        store.write_text(f"{prefix}.md", "\n\n".join(lines) + "\n")
        history = store.state["review_history"] + [{"cycle": cycle, "status": review["status"],
                   "provider": assignment.provider, "session_id": actual_id, "artifact": f"{prefix}.json",
                   "snapshot_tree": self.evidence.snapshot_tree,
                   "validation_artifact": f"validation/cycle-{self.attempt:02d}/results.json", "at": utc_now()}]
        if self.browser is not None:
            history[-1]["browser_artifact"] = f"browser/cycle-{self.attempt:02d}/results.json"
        store.update(review_history=history, final_review_status=review["status"])
        self.active_adapter = plan.adapter
        return review

    def _verify_snapshot(self, role: str) -> None:
        self._verify_frozen_brief()
        after = capture(self.git, self.plan.worktree, self.plan.run_dir / f"checks/{role}-{self.attempt:02d}", self.plan.base_commit)
        self._verify_protected_refs()
        if after.branch != self.plan.branch or after.head_commit != self.expected_head:
            self._abort(f"{role}_git_changed", f"{role} changed branch or HEAD", recoverable=False)
        if after.snapshot_tree != self.evidence.snapshot_tree:
            self._abort(f"{role}_modified_worktree", f"{role} changed the implementation snapshot", recoverable=False)

    def _human_block(self, reason: str) -> None:
        actions = ["Resolve the blocking condition, then explicitly run autobuild resume " + str(self.plan.run_dir)]
        if self.browser and any(g["id"] == "missing-browser-coverage" for g in self.browser["gates"]):
            actions = ["Configure enabled required browser gates and start a new run; "
                       "execution configuration is frozen for this preserved run"]
        self.store.transition(RunState.HUMAN_BLOCKED,
                              checkpoint={"committed": False, "reason": reason},
                              human_gate={"reason": reason,
                              "human_action": actions,
                              "at": utc_now()})

    def _finish(self) -> None:
        plan, store = self.plan, self.store
        commit = self._checkpoint()
        store.transition(RunState.COMPLETED, last_commit=commit)

    def _checkpoint(self) -> Optional[str]:
        """Commit the validated snapshot when checkpoint_policy allows it; never asks anyone."""
        plan, store = self.plan, self.store
        self._verify_browser_history()
        self._verify_validation_history()
        if self.validation is None or not self.validation.passed:
            self._human_block("required normal validation failed or is stale")
            raise RunAborted
        if self.browser is None and (plan.browser_gate or plan.config.data["validation"].get("browser_gates")):
            self._human_block("controller browser evidence is missing")
            raise RunAborted
        if (self.browser is not None and (not self.browser["passed"] or
                self.browser["snapshot_tree"] != self.evidence.snapshot_tree or self.browser["attempt"] != self.attempt)):
            self._human_block("required browser evidence failed or is stale")
            raise RunAborted
        self._verify_snapshot("checkpoint")
        decision = decide_checkpoint(
            enabled_in_config=plan.checkpoint_commits, autonomy_execution=plan.gate.execution,
            validation_passed=self.validation is not None and self.validation.passed,
            has_changes=self.evidence is not None and self.evidence.snapshot_tree != self.git.read(
                "rev-parse", "HEAD^{tree}", cwd=plan.worktree).strip(),
            branch_protected=is_protected_branch(plan.branch, plan.config.protected_branches),
        )
        store.update(checkpoint=decision.as_record())
        store.log.info("checkpoint decision: %s (%s)", "commit" if decision.commit else "skip", decision.reason)
        if not decision.commit:
            return store.state.get("last_commit")
        message = (f"autobuild({plan.meta['id']}): {plan.meta['title']}\n\n"
                   f"Autobuild-Run: {plan.run_id}\nAutobuild-Implementer: {plan.assignment.provider}\n")
        commit = self.git.commit_tree_to_branch(plan.worktree, plan.branch, self.evidence.snapshot_tree,
                                                self.evidence.head_commit, message)
        store.log.info("checkpoint commit %s on %s", commit[:12], plan.branch)
        self._verify_protected_refs()
        return commit

    def _stop(self) -> None:
        store = self.store
        store.log.warning("stop requested (interrupt)")
        self.active_adapter.terminate()
        # A terminated provider can still have emitted its actual session ID.
        # Preserve it for explicit resume rather than relying on the provisional UUID.
        try:
            result = self.active_adapter.get_result()
            sessions = copy.deepcopy(store.state["agent_sessions"])
            if sessions and result.session_id:
                sessions[-1] = {**sessions[-1], "session_id": result.session_id, "ended_at": utc_now()}
                fields = {"agent_sessions": sessions}
                if sessions[-1]["role"] == IMPLEMENTER:
                    self.result = result
                    history = copy.deepcopy(store.state["revision_history"])
                    history[-1] = {**history[-1], "session_id": result.session_id, "ended_at": sessions[-1]["ended_at"]}
                    fields["revision_history"] = history
                    store.write_json(f"implementation/cycle-{self.attempt:02d}/result.json", self._result_doc())
                store.update(**fields)
        except (Exception, KeyboardInterrupt):
            store.log.warning("could not recover a final provider result after interrupt; raw logs preserved")
        if store.current in (RunState.FAILED, RunState.COMPLETED, RunState.STOPPED):
            return
        if store.current is not RunState.STOP_REQUESTED:
            store.transition(RunState.STOP_REQUESTED, stop_requested=True)
        store.transition(RunState.STOPPED)

    # --- Helpers ---

    def _browser(self) -> None:
        plan, store = self.plan, self.store
        self.browser = run_browser(run_id=plan.run_id, attempt=self.attempt,
                                  review_cycle=store.state["review_cycle"] + 1, worktree=plan.worktree,
                                  head_commit=self.evidence.head_commit, snapshot_tree=self.evidence.snapshot_tree,
                                  brief_sha256=store.state["brief_sha256"], config=plan.config.data,
                                  run_dir=plan.run_dir, browser_required=plan.browser_gate,
                                  execution_root=self.validation.execution_root if self.validation else None)
        if self.browser is not None:
            artifact = f"browser/cycle-{self.attempt:02d}/results.json"
            record = {"attempt": self.attempt, "review_cycle": self.browser["review_cycle"], "artifact": artifact,
                      "sha256": digest(store.path(artifact)), "snapshot_tree": self.evidence.snapshot_tree,
                      "passed": self.browser["passed"]}
            store.update(browser_history=store.state.get("browser_history", []) + [record])
            self._verify_snapshot("browser")
        if self.validation is not None:
            self.validation.cleanup()

    def _verify_browser_history(self) -> None:
        errors = history_errors(self.plan.run_dir, self.store.state)
        if errors:
            self._abort("browser_evidence_modified", "; ".join(errors), recoverable=False)

    def _verify_validation_history(self) -> None:
        errors = validation_history_errors(self.plan.run_dir, self.store.state)
        if errors:
            self._abort("validation_evidence_modified", "; ".join(errors), recoverable=False)

    def _verify_frozen_brief(self) -> None:
        if hashlib.sha256(self.store.path("brief.md").read_bytes()).hexdigest() != self.store.state["brief_sha256"]:
            self._abort("frozen_brief_modified", "approved brief changed during the run", recoverable=False)

    def _verify_protected_refs(self) -> None:
        after = self.git.protected_refs()
        if after != self.protected_before:
            changed = [b for b in after if after[b] != self.protected_before.get(b)]
            self._abort("protected_branch_modified", "protected branch moved during the run: " + ", ".join(changed),
                        recoverable=False)

    def _abort(self, reason: str, detail: str, *, recoverable: bool = True) -> None:
        if (self.store.current == RunState.REVIEWING and recoverable
                and reason in ("reviewer_failed", "reviewer_unavailable", "invalid_review")
                and self.store.state["review_cycle"] >= self.plan.config.max_review_cycles):
            self.store.log.error("review budget exhausted (%s): %s", reason, detail)
            self._human_block("maximum review cycles reached without PASS; " + reason + ": " + detail)
            raise RunAborted
        self.store.fail(reason, detail, recoverable=recoverable)
        raise RunAborted

    def _result_doc(self) -> Optional[dict[str, Any]]:
        result = self.result
        if result is None:
            return None
        if result.structured_output is not None:
            status = "valid"
        else:
            status = "invalid" if result.output_error and "match schema" in result.output_error else "missing"
        return {
            "schema_version": 1, "run_id": self.plan.run_id, "implementation_id": self.plan.meta["id"],
            "provider": result.provider, "role": IMPLEMENTER, "session_id": result.session_id,
            "exit_code": result.exit_code, "timed_out": result.timed_out, "terminated": result.terminated,
            "duration_seconds": result.duration_seconds, "report_status": status,
            "report_error": result.output_error, "reported": result.structured_output,
        }


def _summary_markdown(doc: Optional[dict[str, Any]]) -> str:
    """implementation/summary.md: the implementer's own account, labelled as such."""
    if doc is None:
        return "# Implementation Summary\n\nThe implementer did not run.\n"
    reported = doc["reported"]
    lines = ["# Implementation Summary", "",
             f"_Reported by the implementer ({doc['provider']}). Supplemental: not evidence._", ""]
    if reported is None:
        return "\n".join(lines + [f"No valid report: {doc['report_error']}", ""])

    def section(title: str, items: list[str]) -> None:
        lines.extend([f"## {title}", ""] + ([f"- {i}" for i in items] or ["- None"]) + [""])

    lines += [reported["implementation_summary"], ""]
    section("Files Changed (reported)", reported["files_changed"])
    section("Tests Reported", [f"`{t['command']}`: {t['outcome']} — {t['details']}" for t in reported["tests_reported"]])
    section("Documentation Changed", reported["documentation_changed"])
    section("Assumptions", reported["assumptions"])
    section("Known Issues", reported["known_issues"])
    return "\n".join(lines)
