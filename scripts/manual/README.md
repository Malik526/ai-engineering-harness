# Manual completion

Run after implementation and documentation reconciliation, before the final
summary. This shared check never stages, commits, creates branches/worktrees or
enters a controller loop. GIT.md governs final reporting. EXECUTION,
DOCUMENTATION, VERIFICATION and SECURITY remain the policy authorities.

## Workflow: one final validation run

1. Implement, running focused checks as needed (the test files, lint or type
   check for what you are changing). Don't run the full final suites yourself.
2. Finish the code and the documentation reconciliation, including the changelog.
   The fingerprint covers every changed file, so any later edit means a new run.
   Write validation notes in documentation without exact counts (for example
   "web suite, lint and build pass"); the counts belong in the summary. A project
   that requires counts in its changelog accepts one extra run after adding them.
3. Take a snapshot and write the reconciliation JSON with its fingerprint.
4. Choose the final validation commands (see "Choosing commands" below).
5. Run the check with `--run-validation`. This is the final comprehensive
   verification VERIFICATION.md requires; its evidence is what you report.
6. If the check reports NEEDS_ATTENTION, fix what it names and run the same
   command again. Unchanged, still-passing evidence is reused, not rerun.
7. Write the completion summary from the check's result and evidence (commands,
   statuses, counts from the output summaries), with GIT.md's recommended commit.

Use a fresh task-local directory outside the repository (for example a directory
created by `mktemp -d`). Run from the project root:

```sh
python3 ~/.agents/manual-completion/complete.py --snapshot
python3 ~/.agents/manual-completion/complete.py --evidence /tmp/task/evidence.json \
  --reconciliation /tmp/task/reconciliation.json --commands /tmp/task/commands.json \
  --run-validation
```

The second command is the same for the first run and every recheck.

Create the directory before running. Validation specs use the existing config
schema and its `jsonschema` dependency; use the harness Autobuild venv Python
if the default Python lacks it. No provider SDK is required. Keep evidence/logs outside the repository.
The snapshot returns changed paths with staged/unstaged status and a fingerprint.
Inspect these paths and the final diff, preserving unrelated pre-existing work.
List all acknowledged paths in `expected_paths`; this acknowledges baseline work
without claiming ownership. A new unexpected file produces NEEDS_ATTENTION.

Write reconciliation JSON using the current fingerprint:

```json
{
  "fingerprint": "fingerprint from --snapshot",
  "expected_paths": ["app.py", "CHANGELOG.md"],
  "documentation": {
    "changelog": {"status": "updated", "paths": ["CHANGELOG.md"], "reason": "Recorded feature"},
    "project_state": {"status": "not_applicable", "reason": "No separate project state exists"},
    "evaluation_results": {"status": "not_applicable", "reason": "No recorded result changed"},
    "known_limitations": {"status": "not_applicable", "reason": "No limitation changed"},
    "architectural_decisions": {"status": "not_applicable", "reason": "Existing architecture retained"},
    "implementation_documentation": {"status": "not_applicable", "reason": "No documented interface changed"}
  }
}
```

Decisions and reasons must reflect the task and DOCUMENTATION.md, including
investigation-only changes to authoritative facts. Updated entries must name an
actually changed documentation path. The script verifies presence and freshness,
not conceptual correctness. Do not copy the example's reasons blindly.

## Choosing commands

`commands.json` is a JSON list using existing Autobuild `validation.commands`
specs. Reuse applicable specs from `.autobuild/config.yaml` or the project's
existing test/typecheck/lint/build/local runtime commands, plus any check the
project's own instructions require (for example a production build). Include
runtime smoke checks when VERIFICATION.md requires them. Do not run unsafe
commands merely to satisfy completion.

Keep the set proportional to what changed and what depends on it, following
VERIFICATION.md's risk-based scope and the project's testing instructions:

- documentation only: no commands; Git safety and documentation checks still run;
- code in one area: that area's full suites (tests, lint, typecheck, build);
  leave out suites for areas that share no code with the change;
- shared behavior, cross-module contracts, persistence, storage, authentication,
  security or build/deployment configuration: broaden to every affected area and
  the integration configuration the project documents (for example tests that
  need a database).

A spec's `paths` filter records the command as skipped when no changed file
matches. Record every left-out category in `validation_scope` with a specific
reason. Example:

```json
[{"name": "tests", "kind": "test", "run": "python3 -m pytest", "required": true}]
```

For executable changes, reconciliation must also include `validation_scope`
with `test`, `typecheck`, `lint`, `build` and `runtime`. Each item names required
commands or gives a specific `not_applicable` explanation. For example:

```json
{"validation_scope": {
  "test": {"commands": ["tests"]},
  "typecheck": {"not_applicable": "No typed sources"},
  "lint": {"not_applicable": "Project has no configured linter"},
  "build": {"not_applicable": "No build output"},
  "runtime": {"not_applicable": "Library change, no runnable application"}
}}
```

A missing runtime decision blocks completion; the agent still decides whether
local execution is applicable and safe. One command may cover multiple kinds.

The existing validation runner supports `cwd`, `env`, `timeout_seconds` and
`paths`; unmatched path filters are recorded as skipped. Required failed/error/
timeout results block completion. All applicable specs must be supplied; choosing
applicability remains semantic. Validation that changes repository content requires
reconciliation and fresh validation. The manual report labels evidence as manual
rather than controller-owned. Results from commands the agent ran itself are never
evidence; only this check's own run is.

## When validation runs, is reused or is skipped

The result's `validation_run` says what happened, with `validation_run_reason`:

- `blocked`: a check that doesn't depend on test results already fails (stale or
  missing reconciliation fingerprint, unacknowledged changed files, conflicts or
  an in-progress Git operation, secret-like files, incomplete documentation or
  validation applicability). No command runs; fix the issues and rerun.
- `reused`: `--run-validation` found stored evidence for the same repository
  root, fingerprint and exact command list, with every required command passed,
  the same environment digest, recorded within the last hour. Nothing reruns.
- `executed`: the commands ran, because there was no stored evidence, or it
  failed, or the repository, commands or environment changed, or it is older
  than an hour, or `--fresh-validation` was given.
- `not_requested`: commands were given without `--run-validation`; stored
  evidence is only read. `not_applicable`: no commands were given.

The environment digest is a one-way hash of the environment variables except
shell bookkeeping (`PWD`, `OLDPWD`, `SHLVL`, `_`); values are never stored.
Changes Git and the environment don't show, such as installing dependencies into
an ignored directory or upgrading a tool, are not detected: add
`--fresh-validation` after them.

For documentation/analysis-only work omit `--commands`. Non-document filenames
are conservatively treated as executable changes; for genuinely non-executable
changes provide `validation_not_applicable` with a specific explanation. Missing
validation commands without an explanation block completion. Existing unrelated
code changes can also require an explained exemption or validation.

PASS permits normal reporting. NEEDS_ATTENTION exits 1: correct authorized
omissions and rerun; report security or unavailable-validation blockers. A
secret-like changed filename blocks validation execution. The existing filename
guard is conservative (including sample `.env` files) and is not a content secret
scanner; reuse project secret scanners as required validation commands. Ignored
files and credentials hidden in ordinary filenames are outside this check.
Git conflicts and in-progress merge/rebase/cherry-pick/revert state block completion.

`commit_recommendation_required` reflects pending changes. Follow GIT.md for
wording; set `human_requested_commit: true` only for an explicit current-task
request. The check does not validate the future final message or authorize commits.
No-change work still requires documentation reconciliation but no recommendation.

Claude and Codex invoke this through their owned adapter instructions, installed
by the existing installer. There is no vendor stop hook or deterministic final
message interception: invocation is instructional, results are mechanical.
`AUTOBUILD_RUN_ID` or `AUTOBUILD_WORKTREE` causes an immediate SKIP, before Git or
validation. The Autobuild controller never invokes this layer.
