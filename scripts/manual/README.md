# Manual completion

Run once after implementation, verification and documentation reconciliation,
before the final summary. This shared check never stages, commits, creates
branches/worktrees or enters a controller loop. GIT.md governs final reporting.
EXECUTION, DOCUMENTATION, VERIFICATION and SECURITY remain the policy authorities.

Use a fresh task-local directory outside the repository (for example a directory
created by `mktemp -d`). Run from the project root:

```sh
python3 ~/.agents/manual-completion/complete.py --snapshot
python3 ~/.agents/manual-completion/complete.py --evidence /tmp/task/evidence.json \
  --reconciliation /tmp/task/reconciliation.json --commands /tmp/task/commands.json \
  --run-validation
```

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

`commands.json` is a JSON list using existing Autobuild `validation.commands`
specs. Reuse applicable specs from `.autobuild/config.yaml` or the project's
existing test/typecheck/lint/build/local runtime commands. Include runtime smoke
checks when VERIFICATION.md requires them. Do not run unsafe commands merely to
satisfy completion. Example:

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
applicability remains semantic. Without `--run-validation`, the check only reads
previous evidence and verifies repository/configuration fingerprints. Validation
that changes repository content requires reconciliation and fresh validation.
The manual report labels evidence as manual rather than controller-owned.

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
