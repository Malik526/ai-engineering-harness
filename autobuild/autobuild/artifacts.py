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
    ArtifactSpec("implementation/diff.patch", EVIDENCE, "controller", "git diff of the run branch against its parent"),
    ArtifactSpec("implementation/changed-files.txt", EVIDENCE, "controller", "git diff --name-status against the parent"),
    ArtifactSpec("implementation/validation.json", EVIDENCE, "controller", "Commands the controller re-ran, with exit codes"),
    ArtifactSpec("implementation/summary.md", SUPPLEMENTAL, "implementer", "Implementer's account of the change"),
    ArtifactSpec("browser/results.json", EVIDENCE, "browser_tool", "Browser assertions and console errors"),
    ArtifactSpec("browser/screenshots/", EVIDENCE, "browser_tool", "Screenshots referenced by results.json"),
    ArtifactSpec("review/review-NN.json", DECISION, "reviewer", "Structured review result (review.schema.json)"),
    ArtifactSpec("review/review-NN.md", SUPPLEMENTAL, "reviewer", "Reviewer's narrative for the same cycle"),
    ArtifactSpec("logs/", SUPPLEMENTAL, "controller", "Raw agent and command logs"),
)


def run_directory(runs_root: Path, run_id: str) -> Path:
    """Directory holding every artifact for `run_id`."""
    return runs_root / run_id


def review_artifact_name(cycle: int, suffix: str) -> str:
    """'review/review-02.json' for cycle 2."""
    return f"review/review-{cycle:02d}.{suffix}"
