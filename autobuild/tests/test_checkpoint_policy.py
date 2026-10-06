"""Checkpoint-commit decisions: every rule is deterministic and named in the reason."""

import pytest

from autobuild.git.checkpoint_policy import decide_checkpoint

GOOD = dict(enabled_in_config=True, autonomy_execution="autonomous", validation_passed=True,
            has_changes=True, branch_protected=False)


def test_green_validated_work_on_run_branch_commits_without_asking():
    decision = decide_checkpoint(**GOOD)
    assert decision.commit and decision.as_record() == {"committed": True, "reason": decision.reason}


@pytest.mark.parametrize("override, reason_fragment", [
    ({"enabled_in_config": False}, "disabled in the project config"),
    ({"autonomy_execution": "prepare_only"}, "not autonomous"),
    ({"autonomy_execution": "prohibited"}, "not autonomous"),
    ({"validation_passed": False}, "validation did not pass"),
    ({"has_changes": False}, "no changes"),
    ({"branch_protected": True}, "protected"),
])
def test_each_failing_rule_blocks_the_checkpoint(override, reason_fragment):
    decision = decide_checkpoint(**{**GOOD, **override})
    assert not decision.commit and reason_fragment in decision.reason
