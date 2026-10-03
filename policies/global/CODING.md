# Universal Coding Policy

This file is the vendor-neutral source of truth for coding standards that apply across Claude Code, Codex, and any future local AI agent.

## Scope

- Apply these rules to all software projects unless a project-local instruction file gives a more specific or stricter rule.
- Keep project-specific design systems, business workflows, client website procedures, and historical project memory out of this file.
- Prefer the smallest relevant project or module context before changing code.

## Modularity

- Follow modular programming.
- Every component, utility, hook, section, and meaningful function should live in its own file when the project structure supports it.
- Do not put more than one reusable component in a single file.
- Add abstractions only when they reduce meaningful duplication, clarify ownership, or match an existing local pattern.
- Keep edits scoped to the request and to the module boundaries already present in the codebase.

## Frontend And TypeScript

- Use TypeScript for all new frontend files and throughout frontend projects that already use TypeScript.
- For Next.js projects, prefer this folder structure unless the repository has a stronger local convention:

```text
/components
  /ui          -> Reusable primitives such as Button, Card, Badge, Input
  /layout      -> Header, Footer, Nav, PageWrapper
  /sections    -> Page-level sections such as Hero, Services, About, CTA, FAQ
  /forms       -> Any form components
/hooks         -> Custom React hooks
/lib           -> Utility functions, constants, API helpers
/types         -> TypeScript type definitions
/styles        -> Global styles, theme tokens
```

- Create `index.ts` barrel files in component folders when doing so matches the project import style.
- Components should accept props cleanly and be independently reusable.
- Do not inline styles when the project uses Tailwind, CSS modules, or an equivalent styling system.
- Do not hardcode user-facing strings in components when a content file, translation file, CMS, or equivalent content source exists or should exist.

## Existing Patterns

- Read the surrounding code before editing.
- Prefer existing framework choices, helper APIs, naming conventions, and local architecture over introducing new patterns.
- Use structured parsers or APIs for structured data when available instead of ad hoc string manipulation.
- Preserve public behavior unless the task explicitly asks to change it.
