# AI Engineering Harness — Changelog

## 2026-10-04

### Autobuild 0.2 — Single Implementation Runner

- `autobuild run <brief>` takes one approved GREEN brief through preflight →
  isolated branch and worktree → configured implementer → git evidence →
  controller validation → optional checkpoint commit, then stops for the
  human. Worktrees are always kept. `--dry-run` runs preflight only.
- Preflight (`preflight.py`) only reads and fails with every issue listed:
  config, brief, autonomy gate (dependencies from sibling briefs), configured
  provider health (never substituted), git state, protected-branch policy,
  paths, conflicts, validation-command availability.
- Provider adapters: `adapters/claude.py` (`claude -p`, JSON output, schema,
  controller-assigned session id, guard hook) and `adapters/codex.py`
  (`codex exec`, workspace-write sandbox, output schema, JSONL session id),
  on a shared `SubprocessAdapter` (health check, start, get_result,
  terminate, timeouts, process-group kill). The registry names each adapter.
  Core code stays provider-free; the leak test now covers every module
  outside `adapters/`.
- Guards: controller `GitClient` refuses protected-branch writes; per-run git
  shim and Claude PreToolUse hook enforce a read-only git allowlist for agents
  and confine Claude's file edits to the worktree; protected refs verified
  before and after; runs fail on agent commits, branch changes, no changes,
  or secret-like files.
- Evidence: snapshot through a temporary index (`git.json`,
  `changed-files.txt`, `diff.patch`) taken before validation; the checkpoint
  commit (`autobuild(<id>): <title>`) is built from that exact tree.
- Controller validation from `validation.commands` (substitution, cwd, env,
  timeout, required, path filters); `browser_required` stops at
  HUMAN_BLOCKED. Ctrl-C stops the run (STOP_REQUESTED → STOPPED).
- Contracts: config gains `validation.commands`, `git.checkpoint_commits`,
  `git.default_base_branch`, `git.worktree_root` and
  `limits.implementer_timeout_seconds`. Run state gains `base_commit`,
  `review_mode` and `history`. `READY → FAILED` and, for unreviewed runs
  only, `VALIDATING → COMPLETED` are added. New schemas
  `implementation-report` and `implementation-result`. Artifact layout:
  `implementation/{prompt,result,summary,git,diff,changed-files}` and
  `validation/{results.json,logs/}`.
- Docs: new `RUNNER.md`; ARCHITECTURE, ARTIFACT_CONTRACT, SAFETY_MODEL and
  PROVIDERS updated.
- Fixes found by the new tests: bare `git stash` was allowed; shell builtins
  such as `exit` were reported as missing programs.
- Validation: `pytest` 155 passed (fake provider; no live calls). Live:
  Claude Code completed a disposable-fixture run (branch + worktree, main
  untouched, diff captured, validation passed, checkpoint commit), and its
  guard hook refused `git commit` and an out-of-worktree write in a live
  session. Live Codex ran but failed upstream: CLI 0.114.0 is too old for
  the account's models.

## 2026-10-03

### Autobuild — Provider-Agnostic Agent Roles

- Roles (planner, implementer, reviewer) are now separate from providers.
  `providers/registry.yaml` is the only place concrete providers (Claude Code,
  Codex) are named. A test fails if `autobuild/*.py` mentions one.
- Project config adds a required `agents` block (role → provider) and an
  optional `providers` block (per-provider `command` / `model` overrides).
  Validation rejects unknown providers, providers that don't support their
  role, and overrides for unknown providers. Any combination is valid,
  including one provider in every role.
- Run state `agent_sessions[].agent` and review `reviewer.agent` became
  `provider`, an open registry id instead of a vendor enum. Reviewer
  independence remains session-based, so it holds when the same provider
  implements and reviews.
- New `AgentProvider` / `AgentRequest` / `AgentResult` invocation contract
  (adapters arrive in 0.2) and `autobuild agents <project>`.
- `implementation-planning` is now linked to Claude Code as well, since any
  provider may plan. Its description limits it to the planner role.
- Docs: new `autobuild/docs/PROVIDERS.md`; ARCHITECTURE roles are described
  by role, not vendor.
- Validation: `pytest` 78 passed, covering all four role combinations from the
  brief; `autobuild check` all OK.

### Autobuild 0.1 — Foundation and Execution Contract

- `autobuild/`: deterministic contracts for planner → implementer →
  independent reviewer workflows. It doesn't invoke any agent yet.
- Schemas (JSON Schema 2020-12): project config, implementation brief front
  matter, run state, review, validation results, notification payload. Rules
  encoded in the schemas include: GREEN items have no human or external
  requirements; YELLOW items need a human gate; non-draft briefs need recorded
  approval; PASSED needs at least one review; REVISE needs findings; reviews
  must examine the brief and the git diff.
- `policy/autonomy.yaml` and `policy/safety.yaml` drive the autonomy gate
  (`autobuild gate`) and default-deny operation checks.
- Run state machine with human-only resume, plus config-aware checks: no runs
  on protected branches, branch prefix, review-cycle limit, and reviewer
  sessions must be fresh (never an implementer session).
- Artifact contract separating authoritative evidence, decision records and
  supplemental narrative. Validation counts as evidence only when the
  controller re-ran it.
- Remote stop interface (`StopController`, `STOP_SEQUENCE`), notifier
  interface, payload builder and console renderer. No real providers yet.
- Docs: ARCHITECTURE, AUTONOMY_POLICY, ARTIFACT_CONTRACT, SAFETY_MODEL,
  CONTROL_CONTRACT, NOTIFICATION_CONTRACT, ADR 0001.
- Examples: GREEN, YELLOW and RED briefs, run state, REVISE/PASS reviews,
  validation results.
- `skills/custom/implementation-planning`: planner skill, linked to
  `~/.agents/skills` and `~/.codex/skills`. Not linked to Claude Code, which
  is the default implementer.
- Validation: `pytest` 67 passed, including doc/code consistency tests;
  `autobuild check` all OK.

### Harness — Establish Version-Controlled Harness Repository

- New repository `~/ai-engineering-harness`, the canonical source for reusable
  agent policies, custom skills and harness tooling.
- Global policies (`CODING`, `DOCUMENTATION`, `EXECUTION`, `GIT`, `SECURITY`,
  `VERIFICATION`) moved to `policies/global/`. `~/.agents/<NAME>.md` are now
  symlinks to them, so the existing `~/.claude/CLAUDE.md` and
  `~/.codex/AGENTS.md` adapters work unchanged.
- `scripts/setup/install.py` and `links.manifest`: check / apply / adopt
  runtime symlinks. Never overwrites a differing target. Originals are backed
  up to `~/.agents/.harness-backup/`.
- Docs: `ARCHITECTURE.md` (source of truth, ownership classes, why symlinks),
  `INSTALLATION.md`, `SKILL_MANAGEMENT.md` (inventory and classification).
- Left out on purpose: vendor skills (`sanity-*`, claude.ai synced), runtime
  state, the runtime adapters, and the Growth Agency `lead-capture-data-contract`
  skill.
- Validation: secret scan of migrated files clean; content verified identical
  before adoption; both adapters' policy paths resolve through the links.
