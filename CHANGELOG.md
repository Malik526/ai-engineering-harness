# AI Engineering Harness — Changelog

## 2026-10-04

### Autobuild 0.3 - Independent Review, Revisions And Explicit Resume

- Added provider-neutral fresh review after controller validation: structured
  PASS/REVISE/BLOCK, resumed implementer corrections, revalidation and a hard
  review invocation limit. Same-provider roles use independent reviewer sessions.
- Preserved per-attempt Git trees/diffs, validation/process logs and per-cycle
  decisions/history. Only PASS reaches existing controller checkpoint eligibility;
  BLOCK/budget exhaustion preserve uncommitted work at HUMAN_BLOCKED.
- Claude/Codex support read-only reviewers and implementer session resume. Codex
  projects its API wire schema while retaining full local contract validation.
  Explicit CLI resume checks frozen config/brief, worktree/HEAD/refs and artifacts.
- Added review/resume safety fixtures; updated architecture, runner/provider/
  artifact/safety docs, templates, enforcement matrix and ADR 0003.
- Validation: 308 combined regression tests, CLI core check, installed policy
  audit and diff checks pass.
- Live Codex REVISE -> resumed fix -> revalidate -> fresh PASS completed with
  unchanged fixture main; explicit recovery retained earlier failed-review history.
  Claude-to-Codex live completion remains blocked by Claude's HTTP 429/session
  quota, with no fallback/checkpoint. See `autobuild/docs/EVALUATION_0_3.md`.

### Manual Development - Shared Completion Evidence

- Added a shared lightweight completion check with Git snapshots, validation
  fingerprints, explicit documentation/validation applicability reconciliation,
  PASS/NEEDS_ATTENTION and the canonical Git-policy commit-recommendation flag.
- Both owned runtime adapters invoke the same manifest-installed script. No
  autonomous branches, commits, controller loop or provider stop hook was added.
- Reused the existing validation runner/command schema; extracted the unchanged
  secret-like filename guard for shared use. Autobuild markers return SKIP.
- Documented the evidence contract, architecture decision, enforcement matrix
  and fixture evaluation; invocation and semantic correctness remain instructional.
- Validation: 265 automated fixtures pass across harness and Autobuild, including
  20 manual-completion cases; installed adapter audit and diff checks pass.


### Runtime - Portable Guard Ownership and Completion Adapter

- Added canonical Claude settings, Codex prompt rules and thin adapter fragments
  under `runtime/`; full personal configuration and authentication remain outside
  Git. ADR 0002 records ownership and provider-independent core installation.
- Setup now detects available provider executables, merges owned fragments,
  preserves unrelated settings/rules/routing, repairs stale marked definitions,
  refuses conflicts and supports explicit `--check` and isolated `--home`.
  Provider configuration-root overrides are honored on the real home.
- Installer/audit share reconciliation; audits distinguish PASS, MISSING, STALE,
  CONFLICT and absent-provider SKIP. Checks include the exact canonical Claude
  hook, overlapping permissions, Codex rule drift/forbidden prefixes and global
  adapter overrides. Core setup supports either, both or neither provider.
- Codex's adapter references the canonical Git completion rule. `GIT.md` clarifies
  that the final recommendation is one line and omitted without pending changes
  or when the human explicitly requested the commit.
- Claude's hook now inspects Git aliases through read-only config queries, visible
  shell alias definitions, shell command strings and bounded explicit shell
  scripts. Codex rules also cover separate global options and standard absolute
  Git paths. Opaque subprocesses remain outside guard coverage.
- Updated README, installation, architecture and enforcement matrix; added runtime
  operations docs and an opt-in reproducible manual-fixture evaluator.

### Runtime - Portability and Completion Evaluation

- Fresh-home automated fixtures cover Claude-only, Codex-only, mixed and no-provider
  setups, read-only checks, idempotence, preservation, drift and conflict refusals.
- Codex CLI 0.160.0: 3/3 completed manual edits made no commit, loaded all six
  policies in traces and ended with the required recommendation line. A read-only
  fixture omitted the line; a staged explicit commit reached the approval rule
  and was refused with unattended approvals disabled.
- Claude Code 2.1.289: the live manual edit made no commit and included the final
  recommendation. Its explicit-commit live fixture was blocked by the provider
  session limit before execution; direct registered-hook checks returned ask for
  ordinary, inline-alias and shell-wrapped commits and passed a status read.
- `docs/RUNTIME_GUARD_EVALUATION.md` records evidence, infrastructure failures,
  small-sample limits and known bypasses without claiming airtight prevention.
- Validation: 71 harness script tests and 174 unchanged Autobuild regression
  tests passed; installed-provider setup check, instruction audit and diff
  whitespace check passed.

### Policies - Enforcement Matrix and Deterministic Audit

- Added `docs/POLICY_ENFORCEMENT_MATRIX.md` as the authoritative classification
  of meaningful global policy rules: semantic, deterministic, or hybrid,
  including current mechanisms, gaps, recommended mechanisms, and status.
- Added a root ADR for the policy-as-intent plus deterministic-enforcement
  architecture. It keeps always-on manual development separate from Autobuild
  controls while allowing reliable rules to be backed by hooks, schemas,
  audits, Git guards, and runtime permission mechanisms.
- Added `docs/POLICY_ENFORCEMENT_EVALUATION.md` to record the policy-loading,
  commit-guard, checkpoint, manual-usability, and semantic-rule preservation
  checks for this audit.
- `audit_instructions.py` now verifies that the policy enforcement matrix
  exists, contains the required audit fields, and covers every canonical
  policy in `policies/global/`.
- Docs now link the matrix from README, architecture, and installation notes.
- Validation: added instruction-audit tests for complete matrix coverage and
  missing-policy failure cases.

### Policies — Mode-Aware Commit Rules

- Root ambiguity: `GIT.md` let agents commit "if the active runtime is
  permitted to commit", and permission came from accumulated runtime
  settings. Claude Code held an allow rule for `git commit -m '…'`, so some
  sessions committed and others asked.
- `GIT.md` Commit Workflow is now mode-aware:
  - Manual development never commits unless the human explicitly asks, and ends
    with a `Recommended commit:` line.
  - In Autobuild, only the controller makes checkpoint commits, without asking.
  - Human-gated work stops and preserves; no merge or push without instruction.
- `EXECUTION.md` ties the loop's `report` step to it.
- Deterministic guards:
  - New `scripts/hooks/git_commit_guard.py`, a Claude Code PreToolUse hook that
    answers "ask" for any git invocation whose subcommand is `commit`,
    including `git -C … commit`, which slipped past the plain permission
    pattern in testing.
  - Runtime settings (outside the repo): the Claude allow rule is removed and
    an ask rule plus the hook are added; Codex `default.rules` prompts for
    `git commit`, `git -C` and `git -c`.
  - `audit_instructions.py` now verifies all of these.
- Autobuild: new `checkpoint_policy.py` decides checkpoint commits (config,
  GREEN, validation, changes, unprotected branch). The decision is recorded
  in run state (`checkpoint`) and the report. Supersedes 0.2's no-commit at
  `HUMAN_BLOCKED`: validated GREEN work is now checkpointed before a human
  gate. ADR 0002.
- Validation:
  - `pytest` 174 (autobuild) and 16 (hook) passing; the audit passes, and on
    the old configuration it fails on all three guards.
  - Live, in disposable fixtures:
    - Claude manual edit: no commit, recommended message given.
    - Codex manual edit (3 runs): no commit, but the recommended-commit line
      only in 1 of 2 runs after the wording fix.
    - Claude explicit "commit it": held by the hook, recommended message given.
    - Autobuild GREEN: checkpoint committed without asking, `main` untouched.
    - YELLOW brief: refused at preflight.

### Autobuild — Consolidated Live-Test Fixtures and Safe Cleanup

- Disposable live-verification fixtures now live under one git-ignored
  directory, `autobuild/.test-runtime/` (or `AUTOBUILD_TEST_RUNTIME`), with
  worktrees in sibling `<name>.worktrees`. No more top-level home folders.
- `autobuild fixture create --implementer ID` builds the standard V-1
  fixture (templates in `templates/fixture/`) and writes an ownership marker
  to `.git/autobuild-fixture.json`. `autobuild fixture list` shows each
  fixture's verification status.
- `autobuild fixture clean [NAME...|--all] [--yes]` is a dry run by default.
  It deletes only fixtures whose marker, location, worktree registrations
  and worktree directory all verify, and refuses symlinks, copies, unmarked
  repos, worktrees outside the runtime root, and unknown content.
  `--legacy PATH` handles marker-less `~/autobuild-fixture-*` folders through
  a stricter signature check.
- Validation: `pytest` 166 passed (11 new fixture tests, including each
  refusal). Live: a Claude Code run from a runtime fixture completed with a
  checkpoint commit, the fixture stayed git-ignored, and `clean --all --yes`
  removed it and its worktree. The two legacy home fixtures pass `--legacy`
  verification (dry run); deleting them is left to the human.

### Policies — Always-On Documentation Reconciliation

- Root cause of a missed documentation update: after Codex live verification
  passed on CLI 0.160.0, the agent reported it but asked whether to update the
  changelog. Policy loading was correct. All six global policies reach Claude
  Code through the `~/.agents` symlinks (verified live). The policy was
  ambiguous: the changelog checklist covered only "code-changing" tasks, the
  "incidental exploration/analysis" exemption could cover verification, and
  doc updates were tied to "when the task requests it". It also didn't cover
  facts recorded in a different repository from where the work ran.
- Reproduced with a controlled cross-repo fixture (verification in a
  disposable repo, failing status recorded in the system repo, "report
  whether…" prompt). Old policy: 2/2 sessions saw the stale docs and left
  them ("you only asked me to run the check"). New policy: 2/2 updated the
  changelog and status automatically, without Autobuild.
- `DOCUMENTATION.md`: new always-on "Documentation Reconciliation" section
  (status, results, limitations, decisions; target the system the fact is
  about, wherever the work ran; new dated entries rather than rewrites; don't
  ask for obvious updates; completion checklist). The changelog checklist and
  exemption now cover verification-only tasks.
- `DOCUMENTATION.md` also held a pasted Claude auto-memory record (report
  formatting), predating the harness. It's replaced by a vendor-neutral
  Completion Notes bullet, and the duplicate memory file is removed.
- Codex adapter `~/.codex/AGENTS.md` (outside this repo) was missing
  `EXECUTION.md`; reference added.
- New `scripts/setup/audit_instructions.py`: read-only check that every
  canonical policy is symlinked into `~/.agents`, referenced by both runtime
  adapters, and free of memory records. Negative-tested against a fake home
  with the old drift.
- Known remaining gap: commit behavior after a doc update varies (one session
  commits, another asks), reflecting `GIT.md`'s "if the runtime is permitted
  to commit" wording.

### Autobuild 0.2 — Codex Live Verification Passes

- Supersedes the 0.2 entry's "Live Codex … failed upstream" note. With Codex
  CLI 0.160.0 (npm install, authenticated), a disposable-fixture run with
  `implementer: codex` completed `READY → IMPLEMENTING → VALIDATING →
  COMPLETED` in 52 s. Isolated branch and worktree, valid structured report
  and session id, controller-captured diff, controller validation passed,
  checkpoint commit `autobuild(V-1): …` on the run branch, `main` untouched.
- Both registered providers are now verified live end to end.

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
