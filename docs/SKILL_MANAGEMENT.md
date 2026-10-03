# Skill Management

Skills use the open Agent Skills format: a directory with a `SKILL.md` that
has `name` and `description` front matter. Claude Code and Codex both read
it.

## Current Inventory

| Skill | Location | Class | In this repo |
| --- | --- | --- | --- |
| `implementation-planning` | `skills/custom/` here, linked to `~/.agents/skills` and `~/.codex/skills` | CUSTOM (autobuild planner) | Yes, canonical |
| `sanity-best-practices` | `~/.agents/skills`, linked into `~/.claude/skills` | VENDOR (`sanity-io/agent-toolkit`, tracked in `~/.agents/.skill-lock.json`) | No |
| `sanity-migration` | same | VENDOR (same source) | No |
| `lead-capture-data-contract` | `~/.agents/skills` | CUSTOM, project-specific (Growth Agency) | No, belongs with Growth Agency |
| claude.ai synced skills (`docx`, `pptx`, …) | `~/.claude/skills/synced` | VENDOR (synced by Claude) | No |

## Adding a Custom Skill

1. Create `skills/custom/<name>/SKILL.md`. Keep it about this workflow, and don't re-teach generic capabilities that existing skills already cover (browser automation, git, generic code review).
2. Add one manifest line per runtime that should see it, in `scripts/setup/links.manifest`. Link a skill only to runtimes whose role uses it. A planner-only skill doesn't need to be in the implementer's runtime.
3. Run `scripts/setup/install.py --apply`, then the check mode.
4. Add a CHANGELOG entry and commit.

## Modifying a Skill

Edit it here. The runtime paths are symlinks, so the change is live at once.
Commit it like any other change.

## Customized Vendor Skills

Don't edit installer-managed copies in `~/.agents/skills`. The installer can
overwrite them, and the change would be lost. Instead:

1. Copy the upstream skill to `skills/customized/<name>/`.
2. Add `UPSTREAM.md` next to it, with the source repo, path, commit or hash, and date copied.
3. Commit the unmodified copy first, then the local changes as a separate commit, so the diff against upstream stays visible.
4. Remove or rename the installer-managed copy, then link the customized one into place with the manifest.

## Project-Specific Skills

A skill that encodes one project's or one business's domain (schemas, client
workflows) belongs in that project's repository, not here. Codex reads
repo-level `.agents/skills/` and Claude Code reads `.claude/skills/`.

## When a Skill Gets Its Own Repository

Only when it becomes a standalone tool with its own release cycle, its own
consumers outside this harness, or code large enough to need separate CI.
Until then it stays here.
