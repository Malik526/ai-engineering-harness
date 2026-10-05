# Installation

```text
clone → install.py --apply → core links → available provider skills/guards/adapters → audit
```

## New Machine

```bash
git clone <private-remote> ~/ai-engineering-harness
python3 ~/ai-engineering-harness/scripts/setup/install.py --check
python3 ~/ai-engineering-harness/scripts/setup/install.py --apply
python3 ~/ai-engineering-harness/scripts/setup/audit_instructions.py
```

Setup detects `claude` and `codex` on `PATH`. Claude-only, Codex-only, both,
and neither installations are supported. Missing providers are skipped, including
their runtime-specific skill links. Core policies and shared skills always install.
Rerun setup after installing a provider.

Setup creates missing adapters or appends the canonical managed policy-reference
block to existing adapters. Personal routing remains intact. Codex's block
includes a minimal reminder for the completion format defined in global `GIT.md`.
Claude settings are merged; Codex rules use a managed comment section. No entire
runtime configuration is replaced by a fragment. See [Runtime Guards](RUNTIME_GUARDS.md).

The real-home setup honors `CODEX_HOME` and `CLAUDE_CONFIG_DIR`. Use
`--home /isolated/home` for a fresh-home simulation; this ignores those overrides
and uses the providers available on `PATH`. It does not copy authentication.

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
| `OK` / `PASS` | Canonical link / managed runtime definition matches | No action |
| `MISSING` | Nothing at the target | `--apply` |
| `ADOPTABLE` | Target is an identical copy | `--adopt` |
| `CONFLICT` | Target differs, or links elsewhere | Resolve by hand: merge the differences into the repo, then rerun |
| `NO_SOURCE` | The manifest names a source that doesn't exist | Fix the manifest |
| `STALE` | Harness-owned runtime section differs from canonical content | `--apply` |
| `SKIP` | Provider is absent | Install it later and rerun setup if needed |

The script never overwrites a `CONFLICT`. Its check mode exits non-zero
unless every applicable entry passes, so it doubles as a health check. A provider
conflict prevents all runtime-file writes for that provider; other providers and
core links can proceed. Malformed settings, ambiguous ownership markers, symlink
config files, conflicting permissions and advanced Starlark require manual
reconciliation. Updates identify the file and owned section changed.

## Instruction-Chain Audit

```bash
python3 ~/ai-engineering-harness/scripts/setup/audit_instructions.py
```

This is a read-only check that every policy in `policies/global/` is
symlinked into `~/.agents/`, referenced by installed providers' adapters,
that no policy contains a pasted
agent-memory record, and that `docs/POLICY_ENFORCEMENT_MATRIX.md` covers
every canonical policy. It also compares runtime guards and adapter sections
against canonical fragments and reports `PASS`, `MISSING`, `CONFLICT`, `STALE`
or provider `SKIP`. Run it after adding a policy or editing an adapter.

## Runtime Commit Guards

`GIT.md` says manual development never commits without the human. These
runtime settings reinforce it. Harness-owned definitions live under `runtime/`;
personal configuration remains outside Git. Installer and audit share the same
reconciliation code.

Claude gets the commit ask rule and a marked `PreToolUse` Bash hook pointing to
the canonical script. Codex gets native prompt rules for ordinary commits,
selected separate global-option tokens, and standard absolute Git paths.
Explicitly requested commits retain provider approval; these are not deny rules.

Check the Codex rules with
`codex execpolicy check --rules ~/.codex/rules/default.rules git -C /repo commit`
(expect `prompt`). Run setup and guard tests with
`autobuild/.venv/bin/python -m pytest scripts/tests`.

See [Runtime Guards](RUNTIME_GUARDS.md) for exact ownership, audit scope,
supported aliases/wrappers, limitations, and live-evaluation commands.

## Adding a Link

Add a `<source> <target>` line to `scripts/setup/links.manifest`, then run
`install.py --apply`.

## Manual completion layer

The link manifest installs `scripts/manual/` at `~/.agents/manual-completion`.
The existing owned Claude/Codex adapter merge installs the invocation reminder;
no extra hook, permission rule or provider API is added. Run the normal installer
to reconcile these definitions (check mode reports stale adapters). See
[usage and evidence format](../scripts/manual/README.md). JSON command validation
reuses Autobuild's `jsonschema` dependency; its existing venv is a fallback when
the runtime Python lacks that package. Task evidence/logs stay outside Git.
