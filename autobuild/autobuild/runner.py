"""Single implementation runner (phase 0.2).

brief → preflight → isolated branch + worktree → configured implementer →
git evidence → controller validation → optional checkpoint commit → STOP.

Provider-neutral: the implementer is whatever adapter the project config
assigns. Worktrees are always preserved, on success and on failure.
"""

import fnmatch
import os
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
from autobuild.git_evidence import GitEvidence, capture, post_validation_status
from autobuild.git_shim import write_shim
from autobuild.paths import CORE_ROOT
from autobuild.preflight import RunPlan
from autobuild.prompt_builder import build_prompt
from autobuild.roles import IMPLEMENTER
from autobuild.run_report import format_report
from autobuild.run_store import RunStore, close_logger, utc_now
from autobuild.safety import is_protected_branch
from autobuild.schemas import load_schema, schema_errors
from autobuild.states import RunState
from autobuild.validation_runner import ValidationOutcome, run_validation, substitute

# Files that must never leave the worktree in a diff or commit.
SECRET_PATTERNS = (".env", ".env.*", "*.pem", "*.key", "id_rsa*", "id_ed25519*", "credentials*.json",
                   "*service-account*.json", "auth.json")


class RunAborted(Exception):
    """Stop the run at the current step; the state has already been recorded."""


@dataclass
class RunOutcome:
    state: dict[str, Any]
    run_dir: Path
    report: str


def secret_like(paths: list[str]) -> list[str]:
    return [p for p in paths if any(fnmatch.fnmatch(Path(p).name, pattern) for pattern in SECRET_PATTERNS)]


class Runner:
    def __init__(self, plan: RunPlan):
        self.plan = plan
        self.git = GitClient(plan.project_root, plan.config.protected_branches)
        self.store: Optional[RunStore] = None
        self.result: Optional[AgentResult] = None
        self.evidence: Optional[GitEvidence] = None
        self.validation: Optional[ValidationOutcome] = None
        self.protected_before: dict[str, Optional[str]] = {}

    # --- Entry point ---

    def run(self) -> RunOutcome:
        plan = self.plan
        self.store = RunStore.create(config=plan.config, run_dir=plan.run_dir, run_id=plan.run_id,
                                     implementation_id=plan.meta["id"], brief_path=plan.brief_path)
        try:
            self._create_worktree()
            self._implement()
            self._collect_evidence()
            self._validate()
            self._finish()
        except RunAborted:
            pass
        except KeyboardInterrupt:
            self._stop()
        except Exception as exc:  # noqa: BLE001 — every failure must end in a recorded state
            self.store.log.error("unexpected error:\n%s", traceback.format_exc())
            if self.store.current not in (RunState.FAILED, RunState.STOPPED, RunState.COMPLETED):
                self.store.fail("controller_error", f"{type(exc).__name__}: {exc}")
        report = format_report(self.store.state, self._result_doc(), self.evidence, self.validation, plan)
        self.store.write_text("report.md", report)
        close_logger(self.store)
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

    def _implement(self) -> None:
        plan, store = self.plan, self.store
        project_docs = [plan.config.data["paths"][k] for k in ("project_state", "adr_directory", "roadmap")]
        commands = [{**c, "run": substitute(c["run"], plan.project_root, plan.worktree)} for c in plan.validation_commands]
        prompt = build_prompt(brief_text=(store.path("brief.md")).read_text(), worktree=plan.worktree,
                              branch=plan.branch, base_branch=plan.base_branch, base_commit=plan.base_commit,
                              project_docs=project_docs, validation_commands=commands)
        prompt_file = store.write_text("implementation/prompt.md", prompt)

        real_git = shutil.which("git")
        guard_bin = store.path("guard/bin")
        write_shim(guard_bin, sys.executable, CORE_ROOT)
        session_id = str(uuid.uuid4())
        request = AgentRequest(
            role=IMPLEMENTER, prompt_file=prompt_file, working_directory=plan.worktree,
            output_directory=store.path("logs"), report_schema=load_schema("implementation-report"),
            session_id=session_id, timeout_seconds=plan.implementer_timeout, model=plan.assignment.model,
            env={"PATH": f"{guard_bin}{os.pathsep}{os.environ.get('PATH', '')}", "AUTOBUILD_REAL_GIT": real_git or "git",
                 "AUTOBUILD_WORKTREE": str(plan.worktree), "AUTOBUILD_RUN_ID": plan.run_id,
                 "AUTOBUILD_ROLE": IMPLEMENTER},
        )
        session = {"provider": plan.assignment.provider, "role": IMPLEMENTER, "session_id": session_id,
                   "started_at": utc_now(), "ended_at": None}
        store.transition(RunState.IMPLEMENTING, agent_sessions=[session])
        store.log.info("invoking implementer %s (%s)", plan.assignment.provider, plan.assignment.command)
        plan.adapter.start(request)
        try:
            self.result = plan.adapter.get_result()
        except KeyboardInterrupt:
            plan.adapter.terminate()
            raise
        session.update(session_id=self.result.session_id or session_id, ended_at=utc_now())
        store.update(agent_sessions=[session])
        store.write_json("implementation/result.json", self._result_doc())
        store.write_text("implementation/summary.md", _summary_markdown(self._result_doc()))
        store.log.info("implementer ended: exit=%s timed_out=%s report=%s", self.result.exit_code,
                       self.result.timed_out, "valid" if self.result.structured_output else self.result.output_error)
        self._verify_protected_refs()

    def _collect_evidence(self) -> None:
        plan = self.plan
        self.evidence = capture(self.git, plan.worktree, plan.run_dir, plan.base_commit)
        result = self.result
        if result is not None and not result.succeeded:
            reason = "provider_timeout" if result.timed_out else "provider_failed"
            self._abort(reason, f"implementer exit_code={result.exit_code} timed_out={result.timed_out}; see logs/provider*.log")
        if self.evidence.branch != plan.branch:
            self._abort("branch_changed", f"worktree moved off {plan.branch} (now {self.evidence.branch})")
        if self.evidence.committed_by_agent:
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
                                         changed_files=self.evidence.changed_paths, run_dir=plan.run_dir)
        errors = schema_errors("validation", self.validation.document)
        if errors:
            raise RuntimeError("validation results violate schema: " + "; ".join(errors))
        store.write_json("validation/results.json", self.validation.document)
        after = post_validation_status(self.git, plan.worktree)
        if after != self.evidence.status_porcelain:
            store.write_text("validation/worktree-status-after.txt", after)
            store.log.warning("validation changed the worktree; see validation/worktree-status-after.txt")
        if not self.validation.passed:
            self._abort("validation_failed", "required validation failed: " + ", ".join(self.validation.failed_required))

    def _finish(self) -> None:
        plan, store = self.plan, self.store
        commit = self._checkpoint()
        if plan.browser_gate:
            kept = f"checkpoint {commit[:12]} on {plan.branch}" if commit else f"uncommitted changes in {plan.worktree}"
            store.transition(RunState.HUMAN_BLOCKED, last_commit=commit, human_gate={
                "reason": "browser validation required by the brief; automated browser validation arrives in phase 0.4",
                "human_action": [f"Verify the brief's browser acceptance criteria manually in {plan.worktree}",
                                 f"Then keep or discard the validated work ({kept})"],
                "at": utc_now()})
            return
        store.transition(RunState.COMPLETED, last_commit=commit)

    def _checkpoint(self) -> Optional[str]:
        """Commit the validated snapshot when checkpoint_policy allows it; never asks anyone."""
        plan, store = self.plan, self.store
        decision = decide_checkpoint(
            enabled_in_config=plan.checkpoint_commits, autonomy_execution=plan.gate.execution,
            validation_passed=self.validation is not None and self.validation.passed,
            has_changes=self.evidence is not None and self.evidence.has_changes,
            branch_protected=is_protected_branch(plan.branch, plan.config.protected_branches),
        )
        store.update(checkpoint=decision.as_record())
        store.log.info("checkpoint decision: %s (%s)", "commit" if decision.commit else "skip", decision.reason)
        if not decision.commit:
            return None
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
        self.plan.adapter.terminate()
        if store.current in (RunState.FAILED, RunState.COMPLETED, RunState.STOPPED):
            return
        if store.current is not RunState.STOP_REQUESTED:
            store.transition(RunState.STOP_REQUESTED, stop_requested=True)
        store.transition(RunState.STOPPED)

    # --- Helpers ---

    def _verify_protected_refs(self) -> None:
        after = self.git.protected_refs()
        if after != self.protected_before:
            changed = [b for b in after if after[b] != self.protected_before.get(b)]
            self._abort("protected_branch_modified", "protected branch moved during the run: " + ", ".join(changed),
                        recoverable=False)

    def _abort(self, reason: str, detail: str, *, recoverable: bool = True) -> None:
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
