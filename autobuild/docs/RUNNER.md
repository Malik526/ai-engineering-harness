# Confined Validation And Independent Review Runner (Phase 0.5)

`autobuild run` takes one approved brief through implementation and review and stops
for the human:

```text
brief → preflight → branch + worktree → configured implementer → git evidence
      → normal validation → browser gates → fresh reviewer → PASS + gates PASS → checkpoint → STOP
                                REVISE → resume implementer → revalidate → fresh reviewer
                                BLOCK / cycle limit → HUMAN_BLOCKED
```

The bounded review loop is implemented. Fixable validation failures can drive a
reviewer REVISE cycle; infrastructure ERROR and reviewer PASS over required
non-PASS evidence stop for a human. There is no roadmap rollover, merge, push,
or deployment.

## Usage

```bash
cd <project>
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md --dry-run   # preflight only
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md             # asks before starting
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md --yes --base agent/M4.1-auth
~/.agents/autobuild/bin/autobuild resume <run-id-or-directory> --dry-run
~/.agents/autobuild/bin/autobuild resume <run-id-or-directory>
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
checkpoint independently of reviewer PASS. See `VALIDATION_CONFINEMENT.md`.

**Browser validation** runs next through `validation.browser_gates`. See
`BROWSER_GATES.md` for argv configuration, server lifecycle and confinement.
Required FAIL/ERROR/SKIPPED gates cannot checkpoint, even if reviewer returns PASS.
A brief with `browser_required: true` needs an enabled required browser gate;
missing coverage produces a required SKIPPED record and blocks before checkpoint.
This deliberately supersedes the 0.3 checkpoint-before-manual-browser exception.

## Commits

Agents never commit; only the controller does, and it never asks the human
first. The runner reaches checkpoint eligibility only after independent PASS.
A checkpoint is a commit on the isolated run branch, not a merge, push
or release. `autobuild/checkpoint_policy.py` decides, and the decision and
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
trailers. Browser/review human gates occur before the checkpoint. Outside
Autobuild, manual development never commits automatically
(global `GIT.md`).

## Outcomes

| Final state | When |
| --- | --- |
| `COMPLETED` | Controller validation and independent review passed; checkpointed if eligible. Human owns merge |
| `FAILED` | Provider crash or timeout, no changes, agent commit, branch/ref/evidence tampering, secret-like files, or controller error. `failure.reason` names which |
| `HUMAN_BLOCKED` | Review BLOCK/budget, required validation/browser non-PASS plus reviewer PASS, or missing browser coverage. No non-PASS evidence can checkpoint |
| `STOPPED` | Ctrl-C: the provider process group is terminated and the state recorded. Remote stop arrives in 0.6 |

Every run ends with a summary (also saved as `report.md`): implementation,
provider, status, branch, worktree, files changed, controller validation,
commit, known issues reported by the implementer, and the human's next step.

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
are not a universal audit boundary; see `SAFETY_MODEL.md`.

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
only `max_review_cycles` can change. Exhausted budgets require an explicit
human increase (schema maximum 10); prior cycles are never reset. A surviving
`.controller.lock` must be investigated before a human removes it. Missing
provider sessions fail clearly without fallback to a new session/provider.

Resume checks all preserved normal-validation and browser manifests, log/artifact
hashes and identity records, then runs fresh gates after the resumed implementation.
It never reuses prior PASS for changed source.
Missing gate configuration requires a new run because execution config is frozen.
Protected refs changed by unrelated human work also block resume; start a new
run rather than silently rebasing preserved work.

## Live Verification Fixtures

Live provider checks run against disposable fixture repositories, never a
real project. All fixtures live in one ignored directory,
`autobuild/.test-runtime/` (override with `AUTOBUILD_TEST_RUNTIME`), each with
its worktrees in the sibling `<name>.worktrees`:

```bash
autobuild fixture create --implementer codex     # → .test-runtime/live-<date>-codex
cd <fixture> && autobuild run docs/roadmap/V-1.md --yes
autobuild fixture list
autobuild fixture clean --all                    # dry run: shows what would go
autobuild fixture clean --all --yes              # delete
```

A fixture is a fresh git repo on `main` with the standard V-1 brief
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
