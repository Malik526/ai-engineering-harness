"""State machine shape and transition rules."""

import pytest

from autobuild.schemas import load_schema
from autobuild.states import (
    RESUME_TRANSITIONS,
    STOPPABLE,
    TERMINAL,
    InvalidTransition,
    RunState,
    allowed_targets,
    assert_transition,
    can_transition,
)

S = RunState


def test_enum_matches_schema():
    assert {s.value for s in RunState} == set(load_schema("run-state")["properties"]["state"]["enum"])


def test_happy_path_is_legal():
    path = [S.IDLE, S.PLANNING, S.READY, S.IMPLEMENTING, S.VALIDATING, S.REVIEWING, S.PASSED, S.COMPLETED]
    for source, target in zip(path, path[1:]):
        assert_transition(source, target)


def test_revision_loop_revalidates_before_review():
    assert can_transition(S.REVIEWING, S.REVISING)
    assert can_transition(S.REVISING, S.VALIDATING)
    assert not can_transition(S.REVISING, S.REVIEWING)


def test_cannot_pass_without_review():
    for source in (S.IMPLEMENTING, S.VALIDATING, S.REVISING):
        assert not can_transition(source, S.PASSED)


def test_stop_from_every_stoppable_state_and_only_to_stopped():
    for source in STOPPABLE:
        assert can_transition(source, S.STOP_REQUESTED)
    assert allowed_targets(S.STOP_REQUESTED) == {S.STOPPED}


def test_resume_is_human_only():
    for source, target in RESUME_TRANSITIONS:
        assert not can_transition(source, target)
        assert can_transition(source, target, by_human=True)


def test_completed_is_terminal():
    assert TERMINAL == {S.COMPLETED}
    assert allowed_targets(S.COMPLETED, by_human=True) == frozenset()


def test_invalid_transition_raises():
    with pytest.raises(InvalidTransition):
        assert_transition(S.READY, S.PASSED)
