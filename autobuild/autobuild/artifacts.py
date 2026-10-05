"""The run artifact contract: what lives in runs/<run-id>/, who writes it, and
whether a reviewer may treat it as evidence.

docs/ARTIFACT_CONTRACT.md renders this table for humans; a test keeps the two
in agreement.
"""

from dataclasses import dataclass
from pathlib import Path

# Authority classes.
EVIDENCE = "authoritative_evidence"  # the reviewer may rely on it
DECISION = "decision_record"  # drives the state machine
SUPPLEMENTAL = "supplemental"  # agent narrative; read last, never proof


@dataclass(frozen=True)
class ArtifactSpec:
    path: str  # relative to the run directory; NN = two-digit review cycle
    authority: str
    producer: str  # controller | planner | implementer | reviewer | browser_tool
    description: str


RUN_ARTIFACTS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec("brief.md", EVIDENCE, "planner", "Human-approved brief, frozen at run start; hash in state.json"),
    ArtifactSpec("state.json", DECISION, "controller", "Current run state (run-state.schema.json)"),
    ArtifactSpec("config.json", EVIDENCE, "controller", "Execution configuration frozen at run start; checked on resume"),
    ArtifactSpec("report.md", SUPPLEMENTAL, "controller", "Completion summary derived from the records above"),
    ArtifactSpec("implementation/prompt.md", EVIDENCE, "controller", "Exact input the implementer received"),
    ArtifactSpec("implementation/git.json", EVIDENCE, "controller", "Base/head commits, snapshot tree, git status, untracked files"),
    ArtifactSpec("implementation/diff.patch", EVIDENCE, "controller", "Binary-safe diff of the worktree snapshot against the base commit"),
    ArtifactSpec("implementation/changed-files.txt", EVIDENCE, "controller", "Name-status of the same snapshot"),
    ArtifactSpec("implementation/result.json", SUPPLEMENTAL, "implementer", "How the provider process ended, plus the implementer's report (implementation-result.schema.json)"),
    ArtifactSpec("implementation/summary.md", SUPPLEMENTAL, "implementer", "The implementer's report rendered as Markdown"),
    ArtifactSpec("validation/results.json", EVIDENCE, "controller", "Commands the controller ran, with status and exit codes (validation.schema.json)"),
    ArtifactSpec("implementation/cycle-NN/", EVIDENCE, "controller", "Per-attempt prompts, Git snapshots, diffs, changed files, and supplemental reports"),
    ArtifactSpec("validation/cycle-NN/results.json", EVIDENCE, "controller", "Snapshot/config-bound confined validation results and hashed log manifest for each attempt"),
    ArtifactSpec("validation/cycle-NN/logs/", EVIDENCE, "controller", "Raw stdout/stderr of each confined command, hash-bound by the attempt manifest"),
    ArtifactSpec("browser/cycle-NN/results.json", EVIDENCE, "controller", "Immutable browser gate results, snapshot identity and hashed file manifest"),
    ArtifactSpec("browser/cycle-NN/<gate-id>/evidence.json", EVIDENCE, "controller", "Gate argv, isolated environment hash, outcome, timing and bounded log summaries"),
    ArtifactSpec("browser/cycle-NN/<gate-id>/", EVIDENCE, "controller", "Raw command/service logs and confined screenshots, traces, videos or reports in artifacts/"),
    ArtifactSpec("review/review-NN.json", DECISION, "reviewer", "Structured review result (review.schema.json)"),
    ArtifactSpec("review/review-NN.md", SUPPLEMENTAL, "reviewer", "Reviewer's narrative for the same cycle"),
    ArtifactSpec("review/review-NN-prompt.md", EVIDENCE, "controller", "Evidence-first input to the fresh reviewer"),
    ArtifactSpec("review/review-NN-result.json", SUPPLEMENTAL, "controller", "Reviewer process outcome and raw parsed report, including failed reviews"),
    ArtifactSpec("logs/implementation-NN/", SUPPLEMENTAL, "controller", "Raw implementer process output for each attempt"),
    ArtifactSpec("logs/review-NN/", SUPPLEMENTAL, "controller", "Raw reviewer process output for each review cycle"),
    ArtifactSpec("logs/controller.log", SUPPLEMENTAL, "controller", "Controller step log"),
    ArtifactSpec("logs/provider.log", SUPPLEMENTAL, "controller", "Raw provider stdout"),
    ArtifactSpec("logs/provider.stderr.log", SUPPLEMENTAL, "controller", "Raw provider stderr"),
    ArtifactSpec("guard/bin/git", SUPPLEMENTAL, "controller", "Per-run git guard placed first on the agent's PATH"),
)


def run_directory(runs_root: Path, run_id: str) -> Path:
    """Directory holding every artifact for `run_id`."""
    return runs_root / run_id


def review_artifact_name(cycle: int, suffix: str) -> str:
    """'review/review-02.json' for cycle 2."""
    return f"review/review-{cycle:02d}.{suffix}"
