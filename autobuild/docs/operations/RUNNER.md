# Governed Runner: Confined Validation, Independent Review, Rollover (Phase 0.7)

`autobuild run` takes one approved brief through implementation and review and stops
for the human:

```text
brief → preflight → branch + worktree → configured implementer → git evidence
      → normal validation → browser gates → fresh reviewer → PASS + gates PASS → checkpoint → STOP
                                REVISE → resume implementer → revalidate → fresh reviewer
                                BLOCK / cycle limit → HUMAN_BLOCKED
implementer quota/session failure → handoff → configured replacement (new session, max 1)
                                  → fresh validation + browser gates → fresh reviewer
```

The bounded review loop is implemented. Fixable validation failures can drive a
reviewer REVISE cycle; infrastructure ERROR and reviewer PASS over required
non-PASS evidence stop for a human. Bounded *provider* rollover (below) can hand
a failed implementer's work to one configured replacement. There is no roadmap
rollover (starting the next brief), merge, push, or deployment.

## Usage

```bash
cd <project>
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md --dry-run   # preflight only
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md             # asks before starting
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md --yes --base agent/M4.1-auth
~/.agents/autobuild/bin/autobuild resume <run-id-or-directory> --dry-run
~/.agents/autobuild/bin/autobuild resume <run-id-or-directory>
~/.agents/autobuild/bin/autobuild resume <run-id-or-directory> --override-limits   # after raising a budget
~/.agents/autobuild/bin/autobuild stop <run-id-or-directory> [--reason TEXT]       # safe remote stop (control.provider file)
~/.agents/autobuild/bin/autobuild stop <run-id-or-directory> --clear               # withdraw a pending stop
~/.agents/autobuild/bin/autobuild evidence <run-directory> --attempt 2
```

Before starting it prints the implementation, autonomy, implementer (with
version), base branch and commit, target branch, worktree, run directory,
validation commands and commit policy. Exit status is 0 only for `COMPLETED`.

## Preflight

Preflight only reads. If any check fails it prints every issue, says
"Autobuild did not start. No branch or worktree was modified.", and creates
nothing.

1. Project config validates, including role → provider assignments.
2. Brief validates (schema plus required sections).
3. Autonomy gate: GREEN, `status: ready`, dependencies done. Dependencies count as done when a sibling brief in the same directory has that `id` and `status: done`.
4. Both configured implementer and reviewer adapters load and pass health checks. Autobuild never switches providers.
5. The project root is a git top level, with no merge or rebase in progress, and a clean working tree when `require_clean_git_before_start` is set.
6. The base branch exists and is either protected (e.g. `main`) or an automation branch (`<branch_prefix>*`). The run branch is never protected.
7. `project_state` and `adr_directory` exist. A missing `roadmap` is only a warning.
8. The worktree root is outside the project and the worktree path is free.
9. Validation contracts are well formed, runtime dependency paths are present and safe, and a brief with `tests_required` has at least one `test` command. Executable availability is checked inside confinement; a missing tool records ERROR.

## Git Isolation

- **Branch:** `<branch_prefix><id>-<title-slug>`, e.g. `agent/M4.2-instagram-posts`. It's deterministic and checked by `git check-ref-format`, with `-2`, `-3`, … appended if the name already exists.
- **Run id:** `<YYYY-MM-DD>-<id>[-n]`. **Worktree:** `<worktree_root>/<run-id>`. The default root is `<project>.worktrees` next to the project, and it must be outside the project so test discovery never walks into it.
- The run state records `parent_branch`, `branch`, `worktree` and `base_commit`. Before the implementer starts, the controller confirms the worktree exists, is on the run branch, and is at the base commit.
- Worktrees are **never deleted** by autobuild, whatever the outcome.

## Implementer Invocation

The controller writes `implementation/prompt.md` from
`templates/implementer-prompt.md`. The prompt contains the frozen brief,
worktree rules, pointers to the global policies and project docs, the
validation commands, and the completion-output contract. No earlier
conversation is included. The configured adapter runs the provider
non-interactively in the worktree. Its final answer must match
`schemas/implementation-report.schema.json`. The controller stores it in
`implementation/result.json` with the observed exit code, timeout, duration
and session id. It's **supplemental**: an invalid or missing report is
recorded but never decides the outcome.

## Guards

Defense in depth. No single layer is trusted alone:

| Layer | What it stops |
| --- | --- |
| `GitClient` (controller) | Every controller ref write refuses protected branches |
| Git shim on the agent's PATH | Git subcommands outside a read-only allowlist (`commit`, `push`, `merge`, `rebase`, `reset`, `checkout <branch>`, `branch -D`, `update-ref`, `config` writes, `--git-dir`, `-C` outside the worktree, …) |
| Provider confinement | Codex: `workspace-write` sandbox (writes confined to the worktree, no network). Claude Code: a PreToolUse hook applying the same git allowlist to Bash and refusing Edit/Write outside the worktree, plus `--permission-prompts none` and web tools disabled |
| Protected-ref check | The tips of protected branches are compared before and after the agent and after the commit. Any change fails the run as unrecoverable |
| Evidence checks | The run fails if the agent committed, left the run branch, made no changes, or produced secret-like files (`.env`, keys, credentials) |

Known gap: Claude Code's OS-level sandbox needs bubblewrap and socat. Without
them, a Bash command that writes outside the worktree by a non-git route isn't
blocked, only detected if it touches protected refs. Install both to enable
that sandbox in a later phase.

## Controller Validation

After the implementer finishes, the controller snapshots the worktree
(`git.json`, `changed-files.txt`, `diff.patch`), materializes that exact Git tree
into a disposable workspace, and runs `validation.commands` there through the
shared mandatory Bubblewrap backend. Each command
supports:

| Field | Meaning |
| --- | --- |
| `name`, `kind` | Stable id and `kind` in setup, test, lint, typecheck, build, other |
| `command` | Preferred explicit argv. `${PROJECT_ROOT}` and `${WORKTREE}` resolve to the disposable snapshot |
| `run` | Legacy shell string, still confined; mutually exclusive with `command` |
| `cwd` | Repository-relative directory |
| `env` | Explicit variables only; reserved loader/path/proxy/controller keys are rejected and values are not written to evidence |
| `timeout_seconds` | Default 1800 |
| `required` | Default true. Only failing required commands fail the run |
| `network` | `none` by default; `host` is an explicit, evidence-visible opt-in |
| `paths` | fnmatch patterns. Nonmatching commands are recorded SKIPPED |

The sandbox exposes a minimal system/runtime tool set, the snapshot, explicit
read-only `validation.runtime_paths`, and private writable workspace/home/cache/
temp/scratch paths. It does not expose the real worktree, Git metadata, user home,
SSH material, unrelated repositories, or inherited credentials. All commands run
even after failure and share the disposable workspace so setup/build output can be
consumed by later commands and browser gates. It is destroyed after the attempt.

Results and hashed stdout/stderr logs go to `validation/cycle-NN/`, with a latest
`validation/results.json` alias. Missing Bubblewrap/tool/mount, policy/setup errors,
and timeouts are ERROR; nonzero command exits are FAIL. There is no unsandboxed
fallback. Required non-PASS reaches review for possible REVISE but blocks every
checkpoint independently of reviewer PASS. See [VALIDATION_CONFINEMENT.md](../safety/VALIDATION_CONFINEMENT.md).

**Browser validation** runs next through `validation.browser_gates`. See
[BROWSER_GATES.md](BROWSER_GATES.md) for argv configuration, server lifecycle and confinement.
Required FAIL/ERROR/SKIPPED gates cannot checkpoint, even if reviewer returns PASS.
A brief with `browser_required: true` needs an enabled required browser gate;
missing coverage produces a required SKIPPED record and blocks before checkpoint.
This deliberately supersedes the 0.3 checkpoint-before-manual-browser exception.

## Commits

Agents never commit; only the controller does, and it never asks the human
first. The runner reaches checkpoint eligibility only after independent PASS.
A checkpoint is a commit on the isolated run branch, not a merge, push
or release. `autobuild/git/checkpoint_policy.py` decides, and the decision and
reason are recorded in `state.json` → `checkpoint` and in the report. The
controller commits only when all of these hold:

1. `git.checkpoint_commits: true` in the project config (default false);
2. the work is GREEN (autonomy execution `autonomous`);
3. required controller validation passed;
4. the snapshot has changes;
5. the run branch is not protected.
6. required browser gates PASS on this exact attempt/snapshot, and preserved
   browser evidence/artifacts still match the controller's hash records.
7. normal-validation evidence for this exact attempt/snapshot/config and its raw
   log manifest still matches the hashes anchored in `validation_history`.

The commit contains the pre-validation snapshot tree, with message
`autobuild(<id>): <title>` and `Autobuild-Run` / `Autobuild-Implementer`
trailers (the active implementer), plus one `Autobuild-Rollover: <from> -> <to>
(<kind>)` per executed rollover. Browser/review human gates occur before the checkpoint. Outside
Autobuild, manual development never commits automatically
(global `GIT.md`).

## Outcomes

| Final state | When |
| --- | --- |
| `COMPLETED` | Controller validation and independent review passed; checkpointed if eligible. Human owns merge |
| `FAILED` | Provider crash or timeout, no changes, agent commit, branch/ref/evidence tampering, secret-like files, or controller error. `failure.reason` names which |
| `HUMAN_BLOCKED` | Review BLOCK/budget, required validation/browser non-PASS plus reviewer PASS, missing browser coverage, an exhausted governance budget, or an implementer provider/session failure whose rollover is blocked or awaits approval. No non-PASS evidence can checkpoint |
| `STOPPED` | Remote stop (`autobuild stop`) or Ctrl-C: the provider process group is terminated, the request acknowledged and the state recorded |

Every run ends with a summary (also saved as `report.md`): implementation,
active implementer (and whom it took over from), reviewer, status, branch,
worktree, files changed, controller validation, rollover history with handoff
paths, commit, known issues reported by the implementer, and the human's next
step. `autobuild evidence RUN` adds state, cycle, current implementer/reviewer,
and verifies every handoff package hash.

## Independent Review And Revision

Every review gets a new adapter and fresh session, including same-provider
roles. Actual returned session IDs must differ from every prior reviewer and
implementer session. Evidence-first prompts include the frozen approved brief,
actual binary diff, changed files, controller validation and relevant project
instruction/state/ADR/architecture pointers. Implementer narrative comes last.

The full review schema enforces PASS / REVISE / BLOCK (legacy BLOCKED accepted).
REVISE carries structured findings with ID, severity, requirement, evidence,
files/locations and correction. The controller persists JSON/Markdown, resumes
the existing implementer with findings plus necessary context, snapshots the
new work, reruns validation and starts a fresh reviewer. A maximum of
`limits.max_review_cycles` invocations prevents infinite loops. BLOCK and budget
exhaustion preserve all work without a checkpoint and require human action.

Codex reviewers use read-only sandboxing with approvals disabled. Claude
reviewers have only Read/Glob/Grep, with Bash/edit/write/web tools denied and a
role-aware hook. The Git shim denies reviewer index/file writes. Controller
tree comparisons detect tracked/non-ignored worktree changes even if a provider
bypasses its restrictions. Ignored outputs and arbitrary process side effects
are not a universal audit boundary; see [SAFETY_MODEL.md](../safety/SAFETY_MODEL.md).

## Explicit Resume

`autobuild resume RUN [--project DIR] [--dry-run]` is a human command, never an
automatic transition. It accepts STOPPED, recoverable FAILED and HUMAN_BLOCKED;
COMPLETED, active and non-recoverable runs are refused. Legacy 0.2 runs lack the
required safety records and cannot resume. Resume preserves run ID, worktree,
branch, session IDs and numbered artifacts, enters READY with human authority,
resumes the implementer, then validates and uses a new reviewer.

Preflight verifies the frozen brief hash, recorded branch/HEAD/repository,
protected refs, artifact presence, no Git operation/secret-like changes, and
configured providers. Execution configuration must match the frozen copy;
only governance budgets (`limits.max_*`, `rollover.max_rollovers`) can change,
and only with `--override-limits`; each override is recorded in
`state.governance.overrides`. A budget that is already used up refuses to
resume until it is raised and overridden; prior counters are never reset. A surviving
`.controller.lock` must be investigated before a human removes it. Missing
provider sessions are classified `session_unavailable`; without a configured
rollover the run stops with a handoff, never a silent new session/provider.

Resume checks all preserved normal-validation and browser manifests, log/artifact
hashes and identity records, then runs fresh gates after the resumed implementation.
It never reuses prior PASS for changed source.
Missing gate configuration requires a new run because execution config is frozen.
Protected refs changed by unrelated human work also block resume; start a new
run rather than silently rebasing preserved work.

Resume continues the **active** implementer: the configured one, or the
replacement an executed rollover installed. `autobuild resume --dry-run` prints
`Resume mode: same-session` or the rollover it will perform.

## Rollover (0.6)

Same-session resume and rollover are different things and are recorded
differently (`revision_history[].mode`):

| | Same-session resume | Rollover |
| --- | --- | --- |
| Session | the recorded session continues (`resume_session_id`) | a new session; no provider memory |
| Trigger | REVISE findings, or a human `autobuild resume` | a classified provider/session failure ([PROVIDERS.md](../architecture/PROVIDERS.md)) |
| Prompt | findings only ("Continue Approved Implementation") | "Take Over An Existing Implementation" + the full implementer prompt + handoff |

When an implementer attempt fails with an eligible kind (quota, hard limit,
unavailable provider, unresumable or exhausted session), the controller:

1. captures the worktree as a snapshot and writes `rollover/rollover-NN/handoff.json`
   (see [ARTIFACT_CONTRACT.md](../contracts/ARTIFACT_CONTRACT.md)), hashed into `state.rollover_history`;
2. decides with `rollover_policy.py`: configured trigger, budget left
   (`max_rollovers`, at most 1), allowed transition (listed replacement; a
   provider-wide failure needs a different provider), replacement healthy now;
3. if blocked, stops HUMAN_BLOCKED with the handoff preserved; if
   `approval: human`, stops with the rollover `prepared` for `autobuild resume`;
4. otherwise re-verifies the handoff against the live repository (package and
   referenced artifact hashes, worktree branch/HEAD/snapshot, brief/config
   hashes, protected refs, budget, transition) and starts the replacement as a
   new session with the takeover prompt. Any mismatch fails
   `rollover_handoff_invalid` (non-recoverable).

The replacement's result then goes through the normal path: fresh Git evidence,
fresh confined validation, fresh browser gates, a fresh reviewer. Earlier
attempts' evidence stays as history and can never authorize the new source.
A later REVISE resumes the *replacement's* session. A second eligible failure
exceeds the budget and blocks. On resume, a `prepared` rollover executes after
re-verification; a `blocked` one is decided again (for example if the
replacement is installed now) and otherwise the original session continues.

## Governance (0.7)

Autonomy is bounded by deterministic, controller-owned limits. The controller
checks them before **every** agent or tool operation (implementation,
normal validation, browser gates, review) and records every operation's timing
and provider-reported usage in `state.governance`:

| Limit | Counts | Stop reason |
| --- | --- | --- |
| `limits.max_runtime_minutes` | active controller time over all sessions (not time blocked on a human) | `runtime_budget_exhausted` |
| `limits.max_review_cycles` | reviewer invocations | `review_budget_exhausted` |
| `limits.max_revision_attempts` | implementer invocations after the first (revision, resume or rollover takeover) | `revision_budget_exhausted` |
| `rollover.max_rollovers` | executed rollovers | `rollover_budget_exhausted` |
| `limits.max_validation_attempts` | confined normal-validation runs | `validation_budget_exhausted` |
| `limits.max_browser_attempts` | browser-gate runs | `browser_budget_exhausted` |
| `limits.max_usage_tokens` | provider-reported tokens (input incl. cache + output) | `usage_budget_exhausted` |

Only review cycles are mandatory; an absent limit is unlimited. While an
implementer or reviewer runs, a watchdog terminates its process group when the
runtime budget runs out or a remote stop arrives ([CONTROL_CONTRACT.md](../contracts/CONTROL_CONTRACT.md)).
Usage is known only after an operation, so one in flight can overshoot the
token budget; a provider that reports no usage is listed as such, and a usage
budget is refused at preflight unless every configured provider reports usage.
Provider cost is recorded only when the provider reports it (Claude), and is
informational: no cost is estimated.

A budget stop ends `HUMAN_BLOCKED` with `stop_reason` naming the limit, its
value and use, preserves the branch, worktree, uncommitted changes and all
evidence, makes no new checkpoint, and notifies `budget_exhausted`. Continuing
requires raising the limit and `autobuild resume RUN --override-limits`.
Preflight rejects impossible combinations (a rollover with zero revision
attempts, an unimplemented stop provider, an email notifier without settings)
and warns when the runtime budget is shorter than one implementer timeout.

Every finished run has exactly one `stop_reason` (`stop_reasons.py`):
`completed`, `human_blocked`, `remote_stop`, `interrupted`, one of the budget
codes above, `provider_failure`, `validation_failure`, `browser_failure`,
`safety_violation`, `no_changes` or `unknown_failure`. A blocked rollover is
`rollover_budget_exhausted` only when the budget was the cause; an unavailable
or disallowed replacement is `provider_failure`. The report shows the stop
reason, every budget against its limit, time by phase and by provider, and any
limit overrides.

## Live Verification Fixtures

Live provider checks run against disposable fixture repositories, never a
real project. All fixtures live in one ignored directory,
`autobuild/.test-runtime/` (override with `AUTOBUILD_TEST_RUNTIME`), each with
its worktrees in the sibling `<name>.worktrees`:

```bash
autobuild fixture create --implementer codex     # → .test-runtime/live-<date>-codex
cd <fixture> && autobuild run docs/roadmap/verification/V-1.md --yes
autobuild fixture list
autobuild fixture clean --all                    # dry run: shows what would go
autobuild fixture clean --all --yes              # delete
```

A fixture is a fresh git repo on `main` with a roadmap index and the standard
`docs/roadmap/verification/V-1.md` brief
("create `autobuild-test.txt` containing `Autobuild 0.2 verification`"),
a controller validation command, checkpoint commits on, and the chosen
provider in every role. Creation writes an ownership marker into
`.git/autobuild-fixture.json`, which is never tracked and never dirties the
tree.

`fixture create --implementer codex --browser` creates the opt-in counter fixture
instead. It pins Playwright with a lockfile and intentionally leaves the first
click handler unwired to exercise real FAIL -> REVISE -> correction -> PASS.
Seed the npm cache (`npm ci --ignore-scripts --no-audit --no-fund` in the fixture)
and install its Chromium (`npx playwright install chromium`) before starting.
Normal controller setup uses offline `npm ci`; browser execution has no external
network. A fixture-local gate `env.FIXTURE_CHROMIUM` may explicitly select an
existing compatible executable inside the approved Playwright browser cache.

`clean` is a dry run unless `--yes` is given. It deletes a fixture only when
all of these hold:

- it's a real directory (not a symlink) directly under the runtime root;
- it has its own `.git` directory and a marker naming autobuild as owner, live verification as purpose, and this exact path (a copied fixture fails);
- every registered worktree sits in its own `<name>.worktrees`;
- that directory holds nothing except those worktrees.

Anything else is reported as `SKIP` with the reasons, and nothing is touched.

Fixtures created before this existed (`~/autobuild-fixture-*`, no marker)
are accepted only through `--legacy PATH`, which instead requires:

- an `autobuild-fixture*` name;
- project name `Autobuild Fixture` and the V-1 brief;
- a single root commit named `fixture`;
- no git remote;
- the same worktree containment checks.

## Environment Notes

- **Snap-packaged CLIs** (e.g. Codex installed with snap) run with a private
  `/tmp` and can't read hidden top-level home directories. Keep projects and
  worktree roots under a normal home path.
- **Shared virtualenvs** with an editable install import the main checkout's
  code. Put the worktree's source first, e.g.
  `env: {PYTHONPATH: "${WORKTREE}/src"}`.
