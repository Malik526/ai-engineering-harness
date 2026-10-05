"""Whether the controller may create a checkpoint commit — decided here, never by an agent.

A checkpoint is a commit of validated work on the run's isolated branch. It is
not a merge, a push, or a release, so when every condition holds the controller
commits without asking. When one fails, the work stays uncommitted in the
worktree and the reason is recorded in the run state.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckpointDecision:
    commit: bool
    reason: str

    def as_record(self) -> dict:
        return {"committed": self.commit, "reason": self.reason}


def decide_checkpoint(*, enabled_in_config: bool, autonomy_execution: str, validation_passed: bool,
                      has_changes: bool, branch_protected: bool) -> CheckpointDecision:
    """Apply the checkpoint rules in order; the first failing rule is the reason."""
    if not enabled_in_config:
        return CheckpointDecision(False, "git.checkpoint_commits is disabled in the project config")
    if autonomy_execution != "autonomous":
        return CheckpointDecision(False, f"autonomy execution is {autonomy_execution}, not autonomous (GREEN)")
    if not validation_passed:
        return CheckpointDecision(False, "controller validation did not pass")
    if not has_changes:
        return CheckpointDecision(False, "no changes to checkpoint")
    if branch_protected:
        return CheckpointDecision(False, "the run branch is protected")
    return CheckpointDecision(True, "GREEN work validated on the isolated run branch")
