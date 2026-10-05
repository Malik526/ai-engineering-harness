# Single Implementation Runner (Phase 0.2)

`autobuild run` takes one approved brief through one implementation and stops
for the human:

```text
brief → preflight → branch + worktree → configured implementer → git evidence
      → controller validation → checkpoint commit (if enabled) → STOP
```

There is no review loop, retry, repair or rollover yet (0.3 and later).

## Usage

```bash
cd <project>
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md --dry-run   # preflight only
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md             # asks before starting
~/.agents/autobuild/bin/autobuild run docs/roadmap/M4.2.md --yes --base agent/M4.1-auth
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
4. The configured implementer's adapter loads and its health check passes. Autobuild never switches to another provider.
5. The project root is a git top level, with no merge or rebase in progress, and a clean working tree when `require_clean_git_before_start` is set.
6. The base branch exists and is either protected (e.g. `main`) or an automation branch (`<branch_prefix>*`). The run branch is never protected.
7. `project_state` and `adr_directory` exist. A missing `roadmap` is only a warning.
8. The worktree root is outside the project and the worktree path is free.
9. Every validation command's program is available, and a brief with `tests_required` has at least one `test` command.

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
(`git.json`, `changed-files.txt`, `diff.patch`) and then runs
`validation.commands` from the project config in the worktree. Each command
supports:

| Field | Meaning |
| --- | --- |
| `name`, `kind` | `kind` ∈ setup, test, lint, typecheck, build, other |
| `run` | Shell command. `${PROJECT_ROOT}` and `${WORKTREE}` are substituted |
| `cwd` | Repository-relative directory |
| `env` | Extra environment (substituted) |
| `timeout_seconds` | Default 1800 |
| `required` | Default true. Only failing required commands fail the run |
| `paths` | fnmatch patterns. The command runs only if a changed file matches; otherwise it's recorded as `skipped` |

All commands run even after a failure. Results, with stdout and stderr logs,
go to `validation/`. If validation changes the worktree, that's recorded in
`validation/worktree-status-after.txt`. A failed required command ends the run
`FAILED`. No repair is attempted.

**Browser validation** isn't implemented yet (0.4). A brief with
`browser_required: true` runs and validates, then stops at `HUMAN_BLOCKED`
with manual steps. It's never marked validated. Its controller-validated work
is still checkpointed on the run branch when the checkpoint rules allow it.

## Commits

Agents never commit; only the controller does, and it never asks the human
first. A checkpoint is a commit on the isolated run branch, not a merge, push
or release. `autobuild/checkpoint_policy.py` decides, and the decision and
reason are recorded in `state.json` → `checkpoint` and in the report. The
controller commits only when all of these hold:

1. `git.checkpoint_commits: true` in the project config (default false);
2. the work is GREEN (autonomy execution `autonomous`);
3. required controller validation passed;
4. the snapshot has changes;
5. the run branch is not protected.

The commit contains the pre-validation snapshot tree, with message
`autobuild(<id>): <title>` and `Autobuild-Run` / `Autobuild-Implementer`
trailers. A run that then stops at a human gate (`HUMAN_BLOCKED`) keeps that
checkpoint. Outside Autobuild, manual development never commits automatically
(global `GIT.md`).

## Outcomes

| Final state | When |
| --- | --- |
| `COMPLETED` | Validation passed; committed if enabled. Unreviewed: the human reviews and merges |
| `FAILED` | Provider crash or timeout, no changes, agent commit, branch moved, protected ref moved, secret-like files, validation failure, controller error. `failure.reason` names which |
| `HUMAN_BLOCKED` | Browser validation required. Validated work is checkpointed first if the rules allow it |
| `STOPPED` | Ctrl-C: the provider process group is terminated and the state recorded. Remote stop arrives in 0.6 |

Every run ends with a summary (also saved as `report.md`): implementation,
provider, status, branch, worktree, files changed, controller validation,
commit, known issues reported by the implementer, and the human's next step.

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
