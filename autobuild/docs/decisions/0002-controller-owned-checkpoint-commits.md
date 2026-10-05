# 0002 — Commits by Mode: Controller Checkpoints Only, Manual Work Never Auto-Commits

**Status:** Accepted, 2026-10-04

## Context

Global `GIT.md` said agents should commit "if the active runtime is permitted
to commit". Permission, though, came from whatever a runtime's settings
happened to allow. A leftover Claude Code allow rule for one quoting of
`git commit -m '…'` made some sessions commit while others asked first.
Autobuild already committed through its controller, but the rule for
human-gated runs was implicit (no commit at `HUMAN_BLOCKED`).

## Decision

- **Manual development** (anything outside an Autobuild run): agents never
  commit unless the human explicitly asks in the conversation. They finish
  with a summary and a `Recommended commit:` line. Runtime guards back this
  deterministically: a Claude Code ask rule plus a PreToolUse hook
  (`scripts/hooks/git_commit_guard.py`, catches `git -C … commit` and similar
  forms), and Codex execpolicy `prompt` rules. `scripts/setup/audit_instructions.py`
  verifies they're in place.
- **Autobuild:** agents' git access stays read-only. The controller alone makes
  checkpoint commits on the isolated run branch, decided by
  `checkpoint_policy.py`: config flag, GREEN, validation passed, changes
  present, branch unprotected. It never asks the human, and it records the
  decision in run state.
- **Human gates:** validated GREEN work is checkpointed before a run stops at
  `HUMAN_BLOCKED`. The gated operation, merge and push stay with the human.

## Consequences

- Commit behaviour no longer depends on accumulated permission clicks, and
  it's identical across providers.
- Every Autobuild run states whether it committed and why.
- An explicit "commit this" in an interactive session triggers a permission
  prompt rather than committing silently. A non-interactive session can't
  commit at all.
