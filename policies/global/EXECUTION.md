# Universal Execution Mode Policy

This file is the vendor-neutral source of truth for how to move from a task brief to
completed work, across Claude Code, Codex, and any future local AI agent.

## Repository Workflow + Policy Compliance

Before implementing, refresh yourself on the repository's existing execution rules and
documentation hierarchy.

Follow the project's global policies, `AGENTS.md`, architecture decisions, evaluation
docs, changelog conventions, and any task-relevant project documentation already present
in the codebase.

The repository is intentionally documented so you do not need to rediscover or re-plan
the entire architecture for every task.

Your workflow should be:

```text
read global policy / AGENTS.md
→ identify the task's relevant subsystem
→ read only the ADRs/docs/evaluations relevant to that subsystem
→ inspect only the necessary code paths
→ implement
→ test
→ update required docs/changelog
→ report
```

Do not scan the entire repository or all documentation by default.

Use the repository's existing docs as the source of truth:

- global policies = behavioral/workflow rules
- `AGENTS.md` = repository-specific operating instructions
- ADRs / decisions = architectural intent and prior decisions
- evaluations = prior validation evidence and known limitations
- changelog = implementation history
- tests = executable behavioral contracts

Load only the context relevant to the current task. Respect the project's
thin-harness / task-scoped-context approach and avoid unnecessarily expanding agent
context.

Do not create a separate planning artifact, plan-mode session, or planning sub-agent
unless:

1. the brief explicitly asks for planning, or
2. implementation reveals a genuine architectural conflict that cannot be resolved
   safely from the existing repository documentation.

If a material conflict is found, report it concisely and reference the relevant existing
policy/ADR/evaluation instead of creating a broad new plan.

Default execution loop:

```text
refresh policies
→ inspect relevant context
→ implement directly
→ verify
→ document
→ report
```

`report` ends the loop in manual development: a completion summary with a
recommended commit message, not a commit (see `GIT.md` → Commit Workflow).
Only the Autobuild controller commits automatically, and only on its isolated
run branch.

The brief already defines the implementation goal. Your job is to execute it within the
repository's established architecture, not to re-design the project before starting.
