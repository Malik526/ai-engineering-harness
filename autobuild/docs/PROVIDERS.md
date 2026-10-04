# Roles and Providers

Autobuild separates **engineering roles**, which are fixed, from the **agent
providers** that fill them, which are configuration.

| Role | Does |
| --- | --- |
| `planner` | Discusses with the human, maintains the roadmap, writes approved briefs |
| `implementer` | Implements one approved brief in its worktree |
| `reviewer` | Independently judges the evidence; returns PASS / REVISE / BLOCKED |

A provider is any local coding agent that autobuild can run non-interactively.
`providers/registry.yaml` lists them, and it's the **only** place concrete
providers are named. Core code works with roles and provider ids, and a test
fails if a provider name appears in `autobuild/*.py`.

## Assigning Providers

In `.autobuild/config.yaml`:

```yaml
agents:
  planner:
    provider: codex
  implementer:
    provider: claude
  reviewer:
    provider: codex

providers:            # optional, per provider id
  claude:
    command: claude   # executable override (default: registry `executable`)
    model: <model id> # default: the provider's own default
```

Any registry provider may fill any role it lists in `roles`, and one provider
may fill all three. All of these are valid:

| Planner | Implementer | Reviewer |
| --- | --- | --- |
| codex | claude | codex |
| claude | claude | claude |
| codex | codex | codex |
| claude | codex | claude |

Changing an assignment is a config edit only. Run
`autobuild agents <project>` to see the resolved assignment.

## Independence When One Provider Fills Several Roles

Reviewer independence comes from the **session**, not from the vendor:

- The reviewer always starts a fresh session (`AgentRequest.resume_session_id` is never set for it).
- A reviewer session id may never be a session the implementer used. `run_state_checks.py` rejects that.
- The reviewer gets the evidence first (`ARTIFACT_CONTRACT.md`) and the implementer's summary last.

A different vendor adds model diversity, which is useful but optional.
Autobuild doesn't require it.

## Invocation Contract

`autobuild/agent_provider.py` defines the contract every adapter implements:

- `health_check()`: a cheap local check (executable found, `--version` succeeds). It never starts a session.
- `start(request)` / `get_result()` / `terminate()`: run non-interactively and report how it ended.
- `AgentRequest`: role, prompt file (sent on stdin), worktree, output directory, report schema, session id, timeout, extra environment, model.
- `AgentResult`: provider, session id, exit code, timed out / terminated, duration, stdout and stderr files, and the parsed structured report.

`autobuild/subprocess_adapter.py` holds the shared process handling: its own
process group, files for stdin/stdout/stderr, timeout and termination.
Provider adapters live in `autobuild/adapters/` and contain everything
provider-specific: flags, confinement, output parsing.

| Adapter | Invocation | Structured output | Session id | Confinement |
| --- | --- | --- | --- | --- |
| `adapters/claude.py` | `claude -p --output-format json` | `--json-schema` | controller-assigned `--session-id` | `acceptEdits`, `--permission-prompts none`, PreToolUse guard hook, web tools off |
| `adapters/codex.py` | `codex exec --json --cd <worktree> -` | `--output-schema` + `--output-last-message` | `thread_id` from the JSONL events | `--sandbox workspace-write` |

The controller loads the adapter named in the registry (`adapter:
module:Class`) for the role being run. A missing or unhealthy configured
provider stops preflight with `Status: unavailable`. Autobuild never falls
back to another provider.

## Adding a Provider

1. Add an entry to `providers/registry.yaml`: id, `display_name`, `executable`, supported `roles`.
2. Add `autobuild/adapters/<id>.py`, usually a `SubprocessAdapter` subclass implementing `build_command()` and `parse_output()`, and set its `adapter` entry in the registry.
3. Assign it to a role in a project config and run `autobuild config <project>`.

No schema change is needed. Provider ids are open strings, validated against
the registry.

## Skills Per Runtime

Role skills are linked into every runtime that might fill the role. The
`implementation-planning` skill is therefore linked to both Claude Code and
Codex. It applies only when the agent is acting as the planner.
