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
- Update relevant project-local documentation or changelogs when the task requests it or when an established local rule requires it.
- Preserve project-local documentation boundaries; do not move historical notes into unrelated global files.

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

Before completing a code-changing task:

1. inspect the canonical changelog;
2. add or update the relevant dated change-set section for the completed
   change;
3. keep documentation/planning changes separate from implementation changes;
4. include relevant verification or migration information when useful;
5. ensure the changelog is included with the intended repository changes.

If no changelog exists in an actively maintained code repository, create one
unless the project explicitly opts out.

## feedback-report-formatting

description: "User wants task summaries/reports as normal chat markdown, not dumped into a fenced code block"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6db1a9e7-f7d3-4616-9806-08799321a245
  modified: 2026-09-18T04:56:38.896Z
---

Do not put final task summaries or structured reports (e.g. "Required Final Report" style output) inside a fenced ``` code block. Write them as normal chat markdown instead — headers, bold labels, bullet lists, short paragraphs. This applies to EVERY summary/report in chat, not just the first one after the feedback was given — re-check this before sending any milestone-report-shaped message, since the habit of copying a brief's fenced template verbatim is strong and has recurred at least once after this feedback was already saved (2026-09-18, milestone 2.1.7 final report).

**Why:** the user said monospace-block reports are hard to read because they have no real formatting (no bold, no distinct headers, everything the same weight).

**How to apply:** even when a task's own instructions specify a literal "report format" template with a code-fenced skeleton (common in this user's milestone-style briefs), translate that structure into normal markdown — e.g. a field like `Overall result: COMPLETE` becomes a bolded label + value in prose/list form, not a line inside a ``` block. Code fences are still fine for actual code, file paths, terminal output, or short inline literals — just not for wrapping an entire prose summary/report. Before sending a "Required Final Report"-style message, scan it for a fenced block wrapping prose fields and convert it.