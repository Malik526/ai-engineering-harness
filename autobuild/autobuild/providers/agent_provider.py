"""Provider-neutral invocation contract every agent adapter implements.

The controller only talks to this interface, selected through the project's
role assignments (provider_loader.py), so swapping providers never touches
orchestration code. Provider-specific command lines, flags and output parsing
live in autobuild/providers/adapters/.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol

from autobuild.providers.provider_failures import ProviderFailure


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    available: bool
    version: Optional[str]
    detail: str  # what was checked, or why the provider is unavailable


@dataclass(frozen=True)
class AgentRequest:
    role: str  # planner | implementer | reviewer
    prompt_file: Path  # assembled by the controller; sent to the agent on stdin
    working_directory: Path  # the run's worktree; the agent must not leave it
    output_directory: Path  # adapter writes raw stdout/stderr and helper files here
    report_schema: Mapping[str, Any]  # JSON Schema the agent's final answer must satisfy
    session_id: Optional[str] = None  # controller-chosen id, used when the provider accepts one
    resume_session_id: Optional[str] = None  # never set for a reviewer (always a fresh session)
    timeout_seconds: int = 3600
    env: Mapping[str, str] = field(default_factory=dict)  # added to the inherited environment; includes the guard settings
    model: Optional[str] = None  # None = the provider's default


@dataclass(frozen=True)
class AgentResult:
    provider: str
    session_id: Optional[str]
    exit_code: Optional[int]  # None when the process never started or was killed
    timed_out: bool
    terminated: bool  # stopped by terminate() (timeout or stop request)
    duration_seconds: float
    stdout_file: Path
    stderr_file: Path
    structured_output: Optional[dict[str, Any]]  # the agent's final report, parsed
    output_error: Optional[str]  # why structured_output is missing, if it is
    failure: Optional[ProviderFailure] = None  # classified cause when the operation did not succeed
    usage: Optional[dict[str, Any]] = None  # provider-reported tokens, normalized; None when not reported

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.terminated


class AgentProvider(Protocol):
    """Runs one agent operation non-interactively and reports how it ended."""

    provider_id: str

    def health_check(self) -> ProviderHealth:
        """Cheap local check that the provider can be invoked. Never starts an agent session."""
        ...

    def start(self, request: AgentRequest) -> None:
        """Begin the operation without blocking."""
        ...

    def get_result(self) -> AgentResult:
        """Block until the operation ends (or times out) and return its result."""
        ...

    def terminate(self) -> None:
        """Stop the running operation. Safe to call at any time, including before start."""
        ...
