# Universal Git Policy

This file is the vendor-neutral source of truth for Git behavior that applies across Claude Code, Codex, and any future local AI agent.

## Repository Boundaries

- Committing only applies when the touched files are inside a Git repository and committing is safe — see Commit Workflow below for when and how completed work actually reaches a commit.
- Do not initialize new repositories solely to satisfy a commit rule.
- Do not commit files outside the relevant repository.
- If required task files are outside any Git repository, state that they could not be committed because Git does not track them.

## Commit Workflow

Who commits depends on the execution mode, never on what a runtime's permission
settings happen to allow. A permission rule that lets a command run without a
prompt is not an instruction to commit.

### Before any commit boundary

1. Inspect `git status`.
2. Preserve unrelated existing changes.
3. Keep the task's modifications scoped and coherent.
4. Update required changelogs, documentation, ADRs, or related records — including `CHANGELOG.md` when applicable.
5. Run the appropriate verification for the touched code.
6. Review the final diff and confirm the change set represents one logical unit of work.

### Manual development (default)

Any work outside an Autobuild run — interactive sessions, one-off agent
invocations, scripts the human started — is manual development:

- Do not run `git commit` unless the human explicitly asks for a commit in the
  current conversation for this change.
- Finish the work: implementation, validation, documentation reconciliation.
- When this task leaves repository changes after validation and documentation
  reconciliation, end the final message with a line starting `Recommended commit:`
  followed on the same line by a concise conventional commit message.
  This applies to every completed repository change, however small, unless the
  human explicitly requested its commit. Omit the line when there are no
  changes requiring a commit. The human commits.
- An explicit request covers only the change it names; it is not standing
  permission for later work.

Example ending:

```text
Task complete and ready to commit.

Changes:
- Replaced Tools navigation with Free Stuff.
- Fixed mobile navigation toggle.

Verification:
- Production build passes.
- Mobile and desktop routes verified.

Recommended commit: fix: refine portfolio navigation and mobile layout
```

### Autobuild runs

Inside an Autobuild run, commits belong to the deterministic controller, not
to any agent:

- Agents (implementer, reviewer, planner) never commit; their git access is read-only.
- The controller creates a checkpoint commit on the run's isolated branch when
  its configuration and policy allow it (GREEN work, controller validation
  passed, `git.checkpoint_commits` enabled, no safety violation). No human
  approval is requested for that commit; it is not a merge or a release.
- After a checkpoint, the run continues or stops as its workflow defines.

### YELLOW, RED, and human-gated work

- Stop as the autonomy policy requires, preserve the work, and report the
  required human action.
- Do not perform the gated operation, merge, or push.
- In an Autobuild run, the controller may still checkpoint completed, validated
  GREEN work on the isolated branch before stopping.

### Never without explicit human instruction

In every mode: no merge into protected branches, no push, no force push, no
history rewriting of shared branches.

## Commit Granularity

Commits should correspond to coherent, completed units of work — not every file edit.

Preferred:

- `fix mobile navigation + verify` -> one commit
- `add Free Stuff routing + verify` -> one commit

Avoid unnecessary micro-commits, such as a separate commit each for a padding tweak, a variable rename, and a lint fix, when they were all done as part of the same task — unless those changes genuinely represent separate logical work.

## Commit Safety

- Do not include credential files, generated secret material, private environment files, or unrelated local changes in commits.
- Respect dirty worktrees. Treat unrecognized changes as user work and do not revert them unless explicitly asked. The user's existing work is always authoritative.
- Do not mix unrelated work into a single commit.
- Do not stage files merely to make the worktree appear clean.
- Avoid destructive Git commands (force-reset, force-push, discarding changes, etc.) unless the user explicitly requests them.
- Do not bypass hooks or skip verification merely to force a commit through.
- Use non-interactive Git commands where possible.

## Commit Messages

- Use these commit message formats:
  - `feat: [description]` for new features.
  - `fix: [description]` for bug fixes.
  - `config: [description]` for configuration changes.
  - `docs: [description]` for documentation updates.
