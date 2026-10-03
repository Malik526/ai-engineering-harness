"""Provider-neutral invocation contract every agent adapter implements.

Phase 0.2 adds one adapter per registry provider (e.g. a module per provider
that builds that CLI's non-interactive command line). The controller only ever
talks to this interface, selected through the project's role assignments, so
swapping providers never touches orchestration code.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol


@dataclass(frozen=True)
class AgentRequest:
    role: str  # planner | implementer | reviewer
    prompt_file: Path  # assembled by the controller from the brief/artifacts
    working_directory: Path  # the run's worktree; the agent must not leave it
    output_directory: Path  # where the adapter writes raw logs and structured output
    resume_session_id: Optional[str] = None  # never set for a reviewer (always a fresh session)
    allowed_operations: tuple[str, ...] = field(default_factory=tuple)  # ids from policy/safety.yaml
    max_turns: Optional[int] = None
    timeout_seconds: Optional[int] = None


@dataclass(frozen=True)
class AgentResult:
    provider: str
    session_id: str
    exit_code: int
    output_file: Path  # the agent's final structured output
    log_file: Path


class AgentProvider(Protocol):
    """Runs one agent operation non-interactively and reports how it ended."""

    provider_id: str

    def run(self, request: AgentRequest) -> AgentResult: ...

    def terminate(self) -> None:
        """Stop the running operation (used by the stop sequence). Must be safe to call at any time."""
        ...
