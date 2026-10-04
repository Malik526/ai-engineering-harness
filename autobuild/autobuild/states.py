"""Run state machine: the states a run can be in and the legal moves between them.

The controller (phase 0.2+) must call `assert_transition` before every state
write. Resume transitions are reserved for a human command (`/resume`) and
are never taken automatically. Diagram and rationale: docs/ARCHITECTURE.md.
"""

from enum import Enum


class RunState(str, Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    READY = "READY"
    IMPLEMENTING = "IMPLEMENTING"
    VALIDATING = "VALIDATING"
    REVIEWING = "REVIEWING"
    REVISING = "REVISING"
    PASSED = "PASSED"
    HUMAN_BLOCKED = "HUMAN_BLOCKED"
    FAILED = "FAILED"
    STOP_REQUESTED = "STOP_REQUESTED"
    STOPPED = "STOPPED"
    COMPLETED = "COMPLETED"


S = RunState

# Forward progress. REVISING means the implementer is addressing review
# findings or failed validation; it always returns through VALIDATING so a fix
# is re-validated before it is re-reviewed.
_FORWARD: dict[RunState, frozenset[RunState]] = {
    S.IDLE: frozenset({S.PLANNING, S.READY}),
    S.PLANNING: frozenset({S.READY, S.IDLE}),
    S.READY: frozenset({S.IMPLEMENTING, S.HUMAN_BLOCKED, S.FAILED}),
    S.IMPLEMENTING: frozenset({S.VALIDATING, S.HUMAN_BLOCKED, S.FAILED}),
    # VALIDATING -> COMPLETED is the implementation-only path (review_mode none);
    # the run-state schema forbids it from claiming a review it never had.
    S.VALIDATING: frozenset({S.REVIEWING, S.REVISING, S.COMPLETED, S.HUMAN_BLOCKED, S.FAILED}),
    S.REVIEWING: frozenset({S.PASSED, S.REVISING, S.HUMAN_BLOCKED, S.FAILED}),
    S.REVISING: frozenset({S.VALIDATING, S.HUMAN_BLOCKED, S.FAILED}),
    S.PASSED: frozenset({S.COMPLETED, S.FAILED}),
    S.HUMAN_BLOCKED: frozenset(),
    S.FAILED: frozenset(),
    S.STOP_REQUESTED: frozenset({S.STOPPED}),
    S.STOPPED: frozenset(),
    S.COMPLETED: frozenset(),
}

# A stop may be requested from any state where work is running or pending.
STOPPABLE: frozenset[RunState] = frozenset(
    {S.PLANNING, S.READY, S.IMPLEMENTING, S.VALIDATING, S.REVIEWING, S.REVISING, S.PASSED, S.HUMAN_BLOCKED}
)

# Human-only: re-enter READY after a gate, a failure, or a stop. The worktree
# and branch are preserved, so the run continues where it left off.
RESUME_TRANSITIONS: frozenset[tuple[RunState, RunState]] = frozenset(
    {(S.HUMAN_BLOCKED, S.READY), (S.FAILED, S.READY), (S.STOPPED, S.READY)}
)

TERMINAL: frozenset[RunState] = frozenset({S.COMPLETED})


class InvalidTransition(ValueError):
    """Raised when a state change is not permitted by the state machine."""


def can_transition(source: RunState, target: RunState, *, by_human: bool = False) -> bool:
    """True when moving from `source` to `target` is legal for the given actor."""
    if target in _FORWARD[source]:
        return True
    if target is S.STOP_REQUESTED and source in STOPPABLE:
        return True
    return by_human and (source, target) in RESUME_TRANSITIONS


def assert_transition(source: RunState, target: RunState, *, by_human: bool = False) -> None:
    """Raise InvalidTransition unless `can_transition` allows the move."""
    if not can_transition(source, target, by_human=by_human):
        actor = "human" if by_human else "controller"
        raise InvalidTransition(f"{source.value} -> {target.value} is not allowed for {actor}")


def allowed_targets(source: RunState, *, by_human: bool = False) -> frozenset[RunState]:
    """Every state reachable from `source` in one legal step."""
    return frozenset(t for t in RunState if can_transition(source, t, by_human=by_human))
