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

## Instruction-Chain Audit

```bash
python3 ~/ai-engineering-harness/scripts/setup/audit_instructions.py
```

This is a read-only check that every policy in `policies/global/` is
symlinked into `~/.agents/`, imported by `~/.claude/CLAUDE.md` and
referenced by `~/.codex/AGENTS.md`, and that no policy contains a pasted
agent-memory record. Run it after adding a policy or editing an adapter.

## Runtime Commit Guards

`GIT.md` says manual development never commits without the human. These
machine-local settings enforce it. They aren't tracked here because the files
also hold personal runtime state, but `audit_instructions.py` checks them.

`~/.claude/settings.json`: no `allow` rule matching `git commit`, plus:

```json
"permissions": { "ask": ["Bash(git commit *)"] },
"hooks": { "PreToolUse": [ { "matcher": "Bash", "hooks": [
  { "type": "command", "command": "python3 ~/ai-engineering-harness/scripts/hooks/git_commit_guard.py", "timeout": 10 }
] } ] }
```

`~/.codex/rules/default.rules`:

```text
prefix_rule(pattern=["git", "commit"], decision="prompt")
prefix_rule(pattern=["git", "-C"], decision="prompt")
prefix_rule(pattern=["git", "-c"], decision="prompt")
```

Check the Codex rules with
`codex execpolicy check --rules ~/.codex/rules/default.rules git -C /repo commit`
(expect `prompt`). Run the hook tests with
`autobuild/.venv/bin/python -m pytest scripts/tests`.

## Adding a Link

Add a `<source> <target>` line to `scripts/setup/links.manifest`, then run
`install.py --apply`.
