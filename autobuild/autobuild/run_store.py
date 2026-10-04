"""A run's directory and state.json: creation, guarded state transitions, artifacts, controller log.

Every state write goes through the state machine and the run-state schema
(plus config-aware checks), so an invalid state is never persisted.
"""

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from autobuild.config import ProjectConfig
from autobuild.run_state_checks import run_state_errors
from autobuild.states import RunState, assert_transition


class StateContractError(RuntimeError):
    """A state write would violate the run-state contract (a controller bug)."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunStore:
    def __init__(self, run_dir: Path, config: ProjectConfig, state: dict[str, Any]):
        self.run_dir = run_dir
        self.config = config
        self.state = state
        self.log = _controller_logger(run_dir)

    @classmethod
    def create(cls, *, config: ProjectConfig, run_dir: Path, run_id: str, implementation_id: str,
               brief_path: Path, review_mode: str = "none") -> "RunStore":
        """Create the run directory, freeze the brief, and write the initial READY state."""
        for sub in ("implementation", "validation/logs", "logs"):
            (run_dir / sub).mkdir(parents=True, exist_ok=False if sub == "implementation" else True)
        frozen = run_dir / "brief.md"
        shutil.copyfile(brief_path, frozen)
        now = utc_now()
        state = {
            "schema_version": 1, "run_id": run_id, "implementation_id": implementation_id,
            "state": RunState.READY.value, "branch": None, "parent_branch": None, "worktree": None,
            "base_commit": None, "review_mode": review_mode,
            "brief_sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
            "started_at": now, "updated_at": now, "review_cycle": 0, "agent_sessions": [],
            "last_commit": None, "next_implementation": None, "stop_requested": False,
            "failure": None, "human_gate": None,
            "history": [{"state": RunState.READY.value, "at": now}],
        }
        store = cls(run_dir, config, state)
        store._write_state()
        store.log.info("run %s created for %s (brief sha256 %s)", run_id, implementation_id, state["brief_sha256"][:12])
        return store

    # --- State ---

    @property
    def current(self) -> RunState:
        return RunState(self.state["state"])

    def update(self, **fields: Any) -> None:
        self.state.update(fields)
        self.state["updated_at"] = utc_now()
        self._write_state()

    def transition(self, target: RunState, *, by_human: bool = False, **fields: Any) -> None:
        assert_transition(self.current, target, by_human=by_human)
        now = utc_now()
        self.state["history"].append({"state": target.value, "at": now})
        self.log.info("state %s -> %s", self.state["state"], target.value)
        self.update(state=target.value, **fields)

    def fail(self, reason: str, detail: str, *, recoverable: bool = True) -> None:
        self.log.error("FAILED (%s): %s", reason, detail)
        self.transition(RunState.FAILED, failure={"reason": reason, "detail": detail, "at": utc_now(),
                                                  "recoverable": recoverable})

    def _write_state(self) -> None:
        errors = run_state_errors(self.state, self.config)
        if errors:
            raise StateContractError("; ".join(errors))
        self.write_json("state.json", self.state)

    # --- Artifacts ---

    def path(self, relative: str) -> Path:
        return self.run_dir / relative

    def write_text(self, relative: str, text: str) -> Path:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, target)
        return target

    def write_json(self, relative: str, data: Any) -> Path:
        return self.write_text(relative, json.dumps(data, indent=2) + "\n")


def _controller_logger(run_dir: Path) -> logging.Logger:
    logger = logging.getLogger(f"autobuild.run.{run_dir.name}.{id(run_dir)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(run_dir / "logs" / "controller.log")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


def close_logger(store: Optional[RunStore]) -> None:
    if store is None:
        return
    for handler in list(store.log.handlers):
        handler.close()
        store.log.removeHandler(handler)
