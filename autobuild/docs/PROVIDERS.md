# Roles and Providers

Autobuild separates **engineering roles**, which are fixed, from the **agent
providers** that fill them, which are configuration.

| Role | Does |
| --- | --- |
| `planner` | Discusses with the human, maintains the roadmap, writes approved briefs |
| `implementer` | Implements one approved brief in its worktree |
| `reviewer` | Independently judges evidence read-only; returns PASS / REVISE / BLOCK |

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
- A reviewer session ID may not repeat across cycles. Actual returned IDs are checked before persistence.
- The reviewer gets the evidence first (`ARTIFACT_CONTRACT.md`) and the implementer's summary last.

A different vendor adds model diversity, which is useful but optional.
Autobuild doesn't require it.

## Invocation Contract

`autobuild/agent_provider.py` defines the contract every adapter implements:

- `health_check()`: a cheap local check (executable found, `--version` succeeds). It never starts a session.
- `start(request)` / `get_result()` / `terminate()`: run non-interactively and report how it ended.
- `AgentRequest`: role, prompt file (sent on stdin), worktree, output directory, report schema, session id, timeout, extra environment, model.
- `AgentResult`: provider, session id, exit code, timed out / terminated, duration, stdout and stderr files, the parsed structured report, and `failure`: the adapter's classification of an unsuccessful run (see Failure Classification).

`autobuild/subprocess_adapter.py` holds the shared process handling: its own
process group, files for stdin/stdout/stderr, timeout and termination.
Provider adapters live in `autobuild/adapters/` and contain everything
provider-specific: flags, confinement, output parsing.

Browser gates (0.4) do not invoke a provider or change adapter behavior. The
controller runs declared project argv in its own sandbox and gives immutable
evidence to any configured reviewer. Reviewers must acknowledge browser_evidence
when present; PASS cannot override required non-PASS gates. Implementer resume
and fresh reviewer identity checks remain unchanged. Since 0.6 a classified
provider/session failure can hand implementation to another configured provider
only through bounded rollover (below); there is still no implicit fallback.

| Adapter | Invocation | Structured output | Session id | Confinement |
| --- | --- | --- | --- | --- |
| `adapters/claude.py` | `claude -p --output-format json` | `--json-schema` | fresh `--session-id`; implementer `--resume <id>` | Implementer: acceptEdits + hook. Reviewer: default mode, Read/Glob/Grep only, Bash/edit/write/web denied. Permission prompts disabled |
| `adapters/codex.py` | `codex --ask-for-approval never exec --json --cd <worktree> -` | `--output-schema` + `--output-last-message` | returned thread_id; implementer `exec ... resume <id>` | Implementer: workspace-write. Reviewer: read-only. No approval escalation |

Resume flags are adapter-owned: [Codex non-interactive sessions](https://learn.chatgpt.com/docs/non-interactive-mode)
and [Claude CLI reference](https://code.claude.com/docs/en/cli-reference).
Codex's wire schema projects the contract into the API's supported structural
subset, requires nullable optional fields and removes unsupported conditional checks.
Its parser omits optional nulls, then validates against the unchanged full local
contract. This preserves PASS/finding/BLOCK/evidence constraints despite the API
restriction documented in [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
Claude retains the full schema. Raw process logs and actual IDs are kept per
attempt/cycle. Both adapters reject reviewer resume requests.

Resolved 2026-10-05 (0.6): Claude Code 2.1.289 rejected the review contract
because its top-level `allOf` conditionals reach the API as a tool
`input_schema`, which may not combine schemas at the top level. Claude can now
serve as reviewer; see Structured Output Portability. The 0.5 finding is kept in
`EVALUATION_0_5.md`; the live proof is in `EVALUATION_0_6.md`.

The controller loads the adapter named in the registry (`adapter:
module:Class`) for the role being run. A missing or unhealthy configured
provider stops preflight with `Status: unavailable`. Autobuild never silently
falls back to another provider; the only provider change is a configured,
bounded rollover (below), recorded with its reason and handoff.

## Structured Output Portability (0.6)

There is one canonical contract per report (`schemas/review.schema.json`,
`schemas/implementation-report.schema.json`). An adapter may change only the
**wire syntax** a CLI accepts, and only by relaxing it:

```text
canonical schema ─▶ adapters/claude_schema.py ─▶ --json-schema   (drops top-level combinators/annotations)
canonical schema ─▶ adapters/codex_schema.py  ─▶ --output-schema (strict subset; optional fields nullable)
provider answer  ─▶ adapter validates against the unchanged canonical schema
                 ─▶ review_contract.normalize_review ─▶ one persisted PASS / REVISE / BLOCK review
```

Constraints a projection drops (for example "REVISE needs findings") are still
enforced by the canonical validation, so a relaxed wire schema can never admit
a semantically different review. A schema a projection cannot express (not a
top-level object, or a top-level `$ref`) is refused rather than guessed. There is
no provider-specific review type: identity, time, BLOCKED→BLOCK, required
evidence, browser acknowledgement and unique finding IDs are applied by
`review_contract.py` to every reviewer's answer.

## Failure Classification (0.6)

When an invocation does not succeed, the adapter classifies it from the CLI's
own error text (Claude: an `is_error` result envelope or stderr; Codex:
top-level `error`/`turn.failed` events or stderr), never from the agent's
answer. Kinds live in `provider_failures.py`:

| Kind | Scope | Rollover trigger |
| --- | --- | --- |
| `quota_exhausted`, `provider_hard_limit`, `provider_unavailable` | provider-wide | yes, to a different provider |
| `session_unavailable`, `session_exhausted` | this session | yes; the same provider may restart if listed |
| `transient`, `schema_rejected`, `timeout`, `interrupted`, `invalid_output`, `unknown` | — | never |

The patterns were checked against real output (`tests/provider_samples/`):
Codex's usage-limit event, Codex and Claude unknown-session errors, and Claude's
schema rejection. An unrecognised message is `unknown`, which never triggers
rollover: classification fails toward stopping for a human.

## Bounded Rollover (0.6)

```yaml
rollover:
  max_rollovers: 1        # per run; 0.6 caps this at 1
  approval: automatic     # or human: prepare the handoff and stop until `autobuild resume`
  implementer: [claude]   # ordered replacements; never a provider not listed here
  on: [quota_exhausted, session_unavailable]  # optional; default: every eligible kind
```

Absent means disabled: an eligible failure still writes a handoff package and
stops HUMAN_BLOCKED. The replacement is a new session that takes over the
preserved worktree; see `RUNNER.md` → Rollover and ADR 0006. Reviewer rollover is
not implemented: reviewers are always fresh sessions, so configure the reviewer
you want explicitly.

## Adding a Provider

1. Add an entry to `providers/registry.yaml`: id, `display_name`, `executable`, supported `roles`.
2. Add `autobuild/adapters/<id>.py`, usually a `SubprocessAdapter` subclass implementing `build_command()` and `parse_output()`, and set its `adapter` entry in the registry.
   If the CLI's structured-output API restricts JSON Schema, project the canonical schema in the adapter (relaxing only) and validate answers against the canonical one.
   Implement `failure_patterns()` (and `provider_error_text()` if errors are not on stderr) from the CLI's real error output, so quota and lost-session failures can be classified.
3. Assign it to a role in a project config and run `autobuild config <project>`.

No schema change is needed. Provider ids are open strings, validated against
the registry.

## Skills Per Runtime

Role skills are linked into every runtime that might fill the role. The
`implementation-planning` skill is therefore linked to both Claude Code and
Codex. It applies only when the agent is acting as the planner.
