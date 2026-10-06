# Safety Model

## Invariant

**Autonomous agents never modify a protected branch.** Protected branches are
listed per project in `git.protected_branches`, initially `main`. All
autonomous work happens on a branch under `git.branch_prefix`, inside a
dedicated worktree. Config validation rejects a prefix that could produce a
protected branch name, and run-state validation rejects a run whose branch is
protected.

## Trust Boundaries

| Boundary | Trusted to | Not trusted to |
| --- | --- | --- |
| Human | Approve plans, merge, handle secrets and accounts, deploy | — |
| Controller (deterministic code) | Enforce policy, isolate work, stop, notify | Make product or architecture judgments |
| Planner | Propose and classify work | Mark its own plan approved |
| Implementer | Edit its assigned worktree | Approve its work; touch anything outside its worktree |
| Reviewer | Judge evidence | Edit code; trust the implementer's narrative |

## Operations

Operation ids live in `policy/safety.yaml`, and `autobuild/safety.py` checks
them. The policy is **default-deny**: an id missing from `allowed` is refused.

Allowed:

- `repo_read`: read the repository
- `worktree_edit`: edit files inside the assigned worktree
- `run_tests`: run the project's test, lint, typecheck and build commands
- `run_dev_server`: run a local development server
- `browser_automation`: drive a browser against local servers
- `docs_update`: update project documentation and changelog
- `commit_to_assigned_branch`: commit on the run's own branch
- `create_child_branch`: branch a dependent item from a reviewed predecessor

Prohibited:

- `merge_protected_branch`: merge into a protected branch
- `push_protected_branch`: push to a protected branch
- `commit_protected_branch`: commit on a protected branch
- `force_push`: force-push any branch
- `delete_remote_branch`: delete remote branches
- `production_deploy`: deploy to production
- `production_db_destructive`: destructive production database operations
- `secret_disclosure`: print, log or transmit secrets
- `filesystem_outside_scope`: read or write outside the approved paths
- `external_purchase`: buy services
- `billing_change`: change billing
- `account_creation`: create external accounts

## Enforcement Layers

The policy files describe intent. They don't confine a running agent on their
own. Real enforcement is layered, so no single layer depends on a model
cooperating.

1. **Policy (0.1).** The schemas, `policy/*.yaml` and validators reject unsafe configuration and state.
2. **Agent confinement (0.2, implemented).** Agents run non-interactively inside their worktree. A per-run git shim on PATH and, for Claude Code, a PreToolUse hook apply one git allowlist (`autobuild/command_guard.py`): read-only git only; agents never commit, push, merge, rebase, reset, or move branches. The hook also refuses file edits outside the worktree. Codex runs in its `workspace-write` sandbox. Timeouts bound every invocation. Details: `RUNNER.md`.
3. **Controller checks (0.2, implemented).** The controller's own git writes refuse protected branches (`GitClient`). Protected branch tips are compared before and after the agent and after the checkpoint commit, and any change fails the run as unrecoverable. Runs also fail if the agent committed, left its branch, or produced secret-like files.
4. **Server-side backstop (human action, recommended now).** Turn on GitHub branch protection for `main` in every project autobuild drives: no direct pushes, no force pushes.
5. **Out-of-band stop.** See `CONTROL_CONTRACT.md`. Stopping never depends on an agent.

## Secrets

Agents never receive secrets through briefs, artifacts or notifications. When
an item needs a new credential it is YELLOW, and the human adds the secret
through the project's approved mechanism. Run directories are git-ignored.

## Independent Review And Resume (0.3)

Reviewers have no code-edit authority: Codex uses read-only sandboxing with
approval escalation disabled; Claude allows Read/Glob/Grep only, denies shell,
edit/write/web tools, and uses a role-aware refusal hook. The Git shim refuses
reviewer index/file writes. After validation and review, the controller compares
snapshot trees, branch/HEAD, frozen brief hash and protected refs. A mutation
fails without committing or restoring potentially valuable work.

These are layered controls, not proof against arbitrary hostile processes.
Snapshots exclude ignored outputs and do not monitor external side effects.
Claude implementer Bash still has the 0.2 OS-confinement gap when bubblewrap/
socat are unavailable. Secret checks remain filename-based, not content scanning.
Provider authentication/quota failures fail clearly, never trigger fallback.

Fresh reviewer identities are checked across cycles and against implementers.
Budgets count all review invocations. Only PASS reaches checkpoint eligibility;
BLOCK/limits stop HUMAN_BLOCKED. Explicit resume checks frozen config/brief,
worktree repository/branch/HEAD, refs and preserved evidence before execution,
and an exclusive run lock prevents concurrent controllers. Resume never reuses
old normal/browser evidence for changed source or automatically clears a human
gate. See ADRs 0003 through 0005.

## Run Governance (0.7)

A run can no longer continue just because a model keeps trying. The controller
enforces runtime, revision, review, rollover, validation, browser and token
budgets before each operation, and stops a running provider from outside its
process when the runtime budget ends or a remote stop arrives. Every governed
stop preserves the branch, worktree, uncommitted changes and evidence, records
a canonical `stop_reason`, makes no checkpoint, and notifies the operator.
Budgets change only by explicit human override on resume, recorded in the run.
Notification delivery is best-effort and can never alter the persisted state.

Limits: validation and browser commands are not interrupted mid-command (they
have their own timeouts); token usage is provider-reported and checked between
operations; the only stop channel is a local file (`autobuild stop`).

## Provider Rollover (0.6)

Rollover changes who implements, never what counts as evidence. It is opt-in
(`rollover` in the project config), capped at one per run, and limited to
classified provider/session failures; bad code, failing validation, REVISE,
timeouts, transient errors, schema rejections and unrecognised errors never
trigger it. The replacement must be listed in the frozen config, support the
implementer role and pass a health check; a provider-wide failure cannot be
"replaced" by the same provider. Anything else blocks for a human with the
work preserved.

Before takeover the controller re-verifies the hashed handoff against the live
worktree, refs and evidence and fails non-recoverably on any mismatch. The
replacement runs under the same guards as any implementer (worktree-only
writes, Git shim, protected-ref checks, no commits). Its output gets fresh
confined validation, browser gates and a fresh reviewer; earlier evidence
cannot authorize it, and the checkpoint records `Autobuild-Rollover`. A
replacement still sees whatever the failed implementer left in the worktree,
including mistakes, which is why it is told to verify rather than trust it.

## Normal Validation Execution (0.5)

Normal tests, lint, type checks, builds, setup, and project checks run through the
same fail-closed Bubblewrap policy builder as browser gates. The controller first
materializes the exact synthetic Git tree into a fresh temporary directory. That
copy is writable, so normal build/test output works, but the real worktree and its
Git metadata are absent. Private writable HOME, TMPDIR, XDG cache/config/state and
`AUTOBUILD_VALIDATION_SCRATCH` paths are destroyed after normal and browser gates.

The minimal root contains the active Python/tool runtime, system executables and
libraries, the read-only worker/request, explicitly configured read-only runtime
paths, and the writable disposable locations. User home, SSH files, unrelated
repositories, parent directories and host runtime sockets are not mounted, and
the root is remounted read-only so writes outside the approved paths fail. The
environment is rebuilt from safe essentials plus explicitly configured keys;
loader/path/proxy/controller keys are reserved. Network is a fresh namespace by
default. `network: host` is an explicit per-command opt-in recorded in evidence.

Missing Bubblewrap, namespace/mount setup, missing executable, invalid runtime
cwd/output, and timeout become ERROR. Nonzero command exit becomes FAIL. Neither
case can trigger host execution. Worker and controller watchdogs terminate process
groups; PID namespace teardown kills detached descendants on every outcome.
Required non-PASS evidence blocks checkpoint even if a reviewer returns PASS.
Historical evidence is hash/source/config bound and cannot authorize changed code.

## Browser Execution (0.4)

Browser commands and their services run in mandatory Linux Bubblewrap user,
network and PID namespaces with capabilities dropped, read-only host/worktree
mounts, private temp/home/runtime-socket paths, a clean explicit environment,
and only a fresh controller-owned runtime/output directory writable. User home
is hidden except approved controller, runtime, worktree and browser-cache assets.
Git metadata is never writable, no external network is available, and namespace
exit kills descendants even if they detach. The controller also terminates
process groups on success, failure, timeout, exception and interruption.
Unavailable namespaces/tools produce ERROR; there is no weaker fallback.

Artifact collection never searches user paths: only fresh output patterns, with
symlink/root-link/hard-link/special-file/traversal/secret-filename rejection,
file-count/byte budgets and no-follow file opens. Raw logs are bounded and reject
links. Required non-PASS browser evidence independently blocks checkpoint.

This does not change provider security. Read-only system/controller assets remain
visible to browser gates; worktree/node_modules content
may already contain sensitive material. Filename checks are not content scanning.
Browser commands must remain trusted project tests, not hostile multi-tenant
workloads; namespaces do not provide resource quotas, syscall filtering or
protection from kernel vulnerabilities. CPU/memory/private-temp exhaustion and
whole-output-tree scanning are not bounded by the artifact-copy budget.
Gate configuration is human-controlled and frozen, not generated by agents.
