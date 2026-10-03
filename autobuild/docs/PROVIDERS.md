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

`autobuild/agent_provider.py` defines the contract each provider adapter
implements: `AgentRequest` (role, prompt file, worktree, output directory,
allowed operations, limits), `AgentResult` (provider, session id, exit code,
output and log files), and `AgentProvider.run()` / `terminate()`. Phase 0.2
adds the first adapters. The controller only ever calls this interface,
chosen by role.

## Adding a Provider

1. Add an entry to `providers/registry.yaml`: id, `display_name`, `executable`, supported `roles`.
2. Add its adapter implementing `AgentProvider` (phase 0.2 and later).
3. Assign it to a role in a project config and run `autobuild config <project>`.

No schema change is needed. Provider ids are open strings, validated against
the registry.

## Skills Per Runtime

Role skills are linked into every runtime that might fill the role. The
`implementation-planning` skill is therefore linked to both Claude Code and
Codex. It applies only when the agent is acting as the planner.
