# Installation

```text
clone repository → run install.py → links created → adapters reference ~/.agents → Claude Code and Codex consume
```

## New Machine

```bash
git clone <private-remote> ~/ai-engineering-harness
python3 ~/ai-engineering-harness/scripts/setup/install.py           # check: shows MISSING links
python3 ~/ai-engineering-harness/scripts/setup/install.py --apply   # create them
```

Then create the two runtime adapters if they don't exist. They're
deliberately not tracked here.

- `~/.claude/CLAUDE.md`: Claude Code's global adapter. Import each policy with an `@~/.agents/<NAME>.md` line, then add any Claude-specific routing.
- `~/.codex/AGENTS.md`: Codex's global adapter. List the `~/.agents/<NAME>.md` paths Codex must follow, then add any Codex-specific routing.

## Existing Machine (Migration)

When a runtime path already holds a regular file identical to the canonical
one, `--adopt` moves the original to `~/.agents/.harness-backup/<timestamp>/`
and replaces it with a link:

```bash
python3 ~/ai-engineering-harness/scripts/setup/install.py --adopt
```

Delete the backup once both runtimes have been checked.

## Statuses

| Status | Meaning | Action |
| --- | --- | --- |
| `OK` | Symlink to the canonical source | — |
| `MISSING` | Nothing at the target | `--apply` |
| `ADOPTABLE` | Target is an identical copy | `--adopt` |
| `CONFLICT` | Target differs, or links elsewhere | Resolve by hand: merge the differences into the repo, then rerun |
| `NO_SOURCE` | The manifest names a source that doesn't exist | Fix the manifest |

The script never overwrites a `CONFLICT`. Its check mode exits non-zero
unless every entry is `OK`, so it doubles as a health check.

## Adding a Link

Add a `<source> <target>` line to `scripts/setup/links.manifest`, then run
`install.py --apply`.
