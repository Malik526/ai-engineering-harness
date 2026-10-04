# Universal Documentation And Context Policy

This file is the vendor-neutral source of truth for documentation, comments, and context boundaries that apply across Claude Code, Codex, and any future local AI agent.

## Context Boundaries

- Load only the smallest relevant project, module, or file context needed for the task.
- Do not indiscriminately read unrelated project changelogs, sibling client histories, unrelated internal-tool histories, or another product workspace's instructions.
- Do not load Growth Agency website instructions while working on FirstMove unless the task explicitly connects the two.
- Keep project-specific knowledge in project-local instructions, docs, changelogs, or skills.
- Do not create a universal changelog or consolidate existing project, client, or internal-tool changelogs.

## Code Comments

- Add a concise comment block at the top of new source files explaining what the file does and why it exists when that is consistent with the repository's style.
- For components, document accepted props and important dependencies in the top comment block when the component is non-trivial.
- Comment functions with a one-line explanation when the function's purpose is not immediately obvious from its name and signature.
- For hooks, document what the hook manages and returns.
- Add inline comments above logic that is not immediately obvious.
- Use short section comments inside longer components when they improve scanning, such as `// --- State ---`, `// --- Handlers ---`, and `// --- Render ---`.
- Remove dead code unless it is intentionally retained, and document why retained dead code remains.

## Completion Notes

- Provide a clear implementation summary after completing a task.
- State what changed, what was built, and what was skipped or deferred.
- Reconcile documentation before reporting completion (see Documentation
  Reconciliation below); never make an obvious required update conditional on
  the user asking for it.
- Preserve project-local documentation boundaries; do not move historical notes into unrelated global files.
- Write completion reports and summaries as normal Markdown (headings, bold
  labels, lists). Do not wrap a prose report in a fenced code block, even when
  a brief shows its report template inside one; fences are for code, paths,
  and terminal output.

## Documentation Reconciliation (Always On)

This applies to every task, with or without an orchestrator such as Autobuild,
including verification-only, investigation, and "report whether…" tasks.

When the work changes an authoritative fact — implementation status, an
evaluation or verification result (including FAIL → PASS or PASS → FAIL), a
known limitation or assumption (resolved, invalidated, or newly found), an
architectural decision, or documented behavior — update the authoritative
documentation for that fact automatically, as part of the same task:

- Target the documentation of the system the fact is about, even when the
  work ran somewhere else (a fixture, sandbox, worktree, or another repository).
- Typical targets: the changelog, project state, evaluations, ADRs, and the
  docs that state the limitation or behavior.
- Record a changed result as a new dated entry that supersedes the old one;
  do not rewrite the historical entry.
- Do not ask whether to make an obvious required update. Ask only when the
  correct target is genuinely ambiguous, and say what the ambiguity is.
- A request to "report" or "verify" defines what to tell the user; it does
  not exempt the documentation update.

Before declaring any implementation, fix, verification, migration, or
architectural task complete:

1. reconcile code changes with project state;
2. reconcile implementation status and results with the changelog;
3. update evaluations if results changed;
4. record architectural decisions where applicable;
5. update other authoritative documentation affected by the work;
6. then report completion, listing the documentation updated.

# Changelog Policy

For any repository containing an actively maintained application, website,
service, automation, library, or other codebase, meaningful changes MUST be
recorded in the repository changelog.

Default location is `CHANGELOG.md` unless the repository defines another
canonical changelog.

Update the changelog for meaningful features, fixes, behavior changes,
architecture changes, integrations, schema/data changes, significant
configuration changes, security changes, operational changes, or meaningful
documentation contracts. Incidental exploration, analysis, or formatting-only
work does not require an entry unless project-local policy says otherwise.
Verification or evaluation that changes a recorded result, status, or
limitation is not incidental: record it.

Structure entries as `date -> distinct change set -> concise details`.

- Use newest dates first.
- Within a date, give each materially distinct task its own `###` heading.
- Prefer `### <Phase/Area> - <Change Name>`; use an em dash when the file's
  character set allows it.
- Optional short commit SHAs may prefix headings when useful for traceability.
- Keep planning/documentation entries separate from actual implementation
  entries.
- Include meaningful validation or migration notes when useful.
- Keep entries project-facing; do not use changelogs as reasoning logs,
  transcripts, task checklists, or copies of diffs.
- Do not rewrite historical entries unless explicitly requested, correcting an
  error, or performing an intentional changelog cleanup.
- Follow explicit project-local formats when present, but do not collapse
  unrelated same-day changes into one ambiguous flat list unless the project
  explicitly requires it.

Before completing any task that changes code or an authoritative project
fact (including verification-only tasks):

1. inspect the canonical changelog;
2. add or update the relevant dated change-set section for the completed
   change;
3. keep documentation/planning changes separate from implementation changes;
4. include relevant verification or migration information when useful;
5. ensure the changelog is included with the intended repository changes.

If no changelog exists in an actively maintained code repository, create one
unless the project explicitly opts out.
