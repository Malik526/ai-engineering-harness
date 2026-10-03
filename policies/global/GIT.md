# Universal Git Policy

This file is the vendor-neutral source of truth for Git behavior that applies across Claude Code, Codex, and any future local AI agent.

## Repository Boundaries

- Committing only applies when the touched files are inside a Git repository and committing is safe — see Commit Workflow below for when and how completed work actually reaches a commit.
- Do not initialize new repositories solely to satisfy a commit rule.
- Do not commit files outside the relevant repository.
- If required task files are outside any Git repository, state that they could not be committed because Git does not track them.

## Commit Workflow

Completed engineering work should end at a clear, logical commit boundary — never ambiguously. It should either be committed, or clearly reported as verified and ready to commit with a proposed commit message.

Before considering a task complete:

1. Inspect `git status`.
2. Preserve unrelated existing changes.
3. Keep the task's modifications scoped and coherent.
4. Update required changelogs, documentation, ADRs, or related records — including `CHANGELOG.md` when applicable.
5. Run the appropriate verification for the touched code.
6. Review the final diff and confirm the change set represents one logical unit of work.

### If the active runtime is permitted to commit

When the active agent/runtime is allowed to create commits without further user authorization:

- create a commit for the completed logical unit of work;
- use a concise commit message describing the actual change;
- do not include unrelated dirty-worktree changes.

### If explicit authorization is required

When the active agent/runtime requires explicit user authorization before `git commit`, do not bypass or work around that restriction.

Instead, once the work is verified and commit-ready:

1. Report that the task is ready to commit.
2. Summarize what changed.
3. List any important verification performed.
4. Propose a concise commit message.
5. Wait for user authorization before running `git commit`.

Example:

```text
Task complete and ready to commit.

Changes:
- Replaced Tools navigation with Free Stuff.
- Fixed mobile navigation toggle.
- Removed duplicate Contact label.
- Added consistent mobile container spacing.

Verification:
- Production build passes.
- Mobile and desktop routes verified.
- Existing lead-capture flow unaffected.

Proposed commit:

`fix: refine portfolio navigation and mobile layout`

Awaiting authorization to commit.
```

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
