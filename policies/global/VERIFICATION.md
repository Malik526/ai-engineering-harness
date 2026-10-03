# Universal Verification Policy

This file is the vendor-neutral source of truth for completion and verification behavior that applies across Claude Code, Codex, and any future local AI agent.

## Required Verification

- Run applicable tests after code changes when the repository provides a test command and running it is safe.
- Run applicable type checking for typed projects when available.
- Run applicable linting or formatting checks when they are part of the project's normal validation path.
- Run applicable build validation for changes that can affect build output.
- Run runnable projects locally before marking changes complete when the task changes a runnable application and local execution is safe.
- Completion verification must include checking that required documentation and
changelog updates were made.
## Reporting

- Explicitly state which verification commands were run.
- If verification is not applicable because the change is documentation-only, configuration-only, or outside a runnable project, say so.
- If verification cannot be performed because of missing dependencies, missing credentials, sandbox restrictions, unsafe side effects, or time constraints, say so clearly and explain the limitation.
- Do not perform destructive project changes merely for verification.

## Risk-Based Scope

- Match verification depth to risk and blast radius.
- Broaden checks for shared behavior, cross-module contracts, user-facing workflows, security-sensitive code, or build/deployment changes.
- Keep checks focused for narrow documentation or local-only edits.
