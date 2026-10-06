# Autobuild 0.6 Evaluation

Evaluation date: 2026-10-05 (America/New_York; run timestamps are UTC). This
record evaluates reviewer portability and bounded implementer rollover.
Providers: Claude Code 2.1.289, Codex CLI 0.160.0.

## Root Cause Of The Claude Reviewer Defect

Claude Code sends `--json-schema` to the API as a tool `input_schema`, which may
not use `oneOf`/`allOf`/`anyOf` at the top level. The review contract's
PASS/REVISE/BLOCK conditionals are a top-level `allOf`, so every Claude review
failed with `API Error: 400 … input_schema does not support oneOf, allOf, or
anyOf at the top level` before reviewing anything. A live probe confirmed the
fix before wiring it in: the projected schema (top-level combinators and
annotations removed, every nested constraint kept) was accepted and returned a
schema-valid review. The canonical schema, including the dropped conditionals,
still validates every answer locally.

## Automated Verification

```sh
cd autobuild
.venv/bin/python -m pytest tests ../scripts/tests -q
bin/autobuild check
python3 ../scripts/setup/audit_instructions.py
git diff --check
```

Result: **438 passed** (389 before 0.6, 49 new), plus the core schema/example
check, instruction audit and whitespace check.

New coverage:

- **Reviewer portability (16):** Claude and Codex projections of the canonical
  schema, projections only relax (canonical-valid documents stay valid),
  refusal of shapes that cannot be projected, Claude command sends the
  projection, PASS/REVISE/BLOCK/BLOCKED from both adapters normalize to the same
  canonical review, malformed/incomplete answers rejected (including a REVISE
  without findings that the relaxed wire schema allows), real CLI error output
  classified (Codex usage limit, Codex and Claude unknown session, Claude schema
  rejection), agent text never mistaken for a provider error, schema rejection
  fails review clearly without rollover.
- **Rollover (32):** quota rollover end to end with handoff contents and hashes,
  rollover during revision with fresh validation, browser gates and reviewer,
  session-scoped same-provider restart; no rollover for transient errors, test
  failures or REVISE; fail-closed for exhausted budget, unsupported transition,
  unavailable replacement, unconfigured rollover and unlisted trigger; human
  approval prepared → resume executes; refusal after handoff, diff, worktree or
  protected-ref tampering; runner refusal when the source changes between
  handoff and takeover; re-decision of a blocked rollover on resume;
  same-session resume of the original and of the replacement; policy and config
  bounds.
- **Prompt (1):** argv validation commands are shown with shell quoting (a
  defect found live, below).

Mutation checks: disabling the handoff's source-identity check or the
provider-wide transition rule makes four rollover tests fail.

## Live Validation

All fixtures live in the ignored `.test-runtime/`, have no remote, and kept
`main` at their base commit. No harness commit, merge or push occurred.

### A. Claude reviewer (defect fixed)

| Fixture | Pairing | Result |
| --- | --- | --- |
| `live-06-claude-review` | Claude → Claude | Confined validation PASS; fresh Claude reviewer `4e06dea6…` PASS; checkpoint `538d1ac301f3` on the run branch; `main` `f0a9c33029b0` unchanged |

### B. Rollover after a real Codex usage limit

`live-06-rollover-quota` (browser counter fixture, single-attempt protocol),
configured implementer Codex, rollover `max 1, automatic, [claude]`, reviewer
Claude. Codex was genuinely out of quota, so this is a real provider failure,
not a simulation:

1. Codex session `01a10a65-6f62…` failed; its `turn.failed` event ("You've hit
   your usage limit…") was classified `quota_exhausted`.
2. The controller wrote and hashed `rollover/rollover-01/handoff.json`
   (failed attempt 1, rollover count 0/1, empty diff, protected refs, brief and
   config hashes), decided `codex quota_exhausted; configured rollover selects
   claude`, re-verified the handoff and started Claude session `96635958…` with
   the "Take Over An Existing Implementation" prompt.
3. Fresh evidence for attempt 2 only: confined validation PASS (setup with
   explicit host network, HTML check with none), real Playwright gate PASS with
   three artifacts, fresh Claude reviewer `f6e2a352…` PASS.
4. Checkpoint `5833ec33aaf4` on the run branch with trailers
   `Autobuild-Implementer: claude` and `Autobuild-Rollover: codex -> claude
   (quota_exhausted)`; `main` `dc1dcf485c3e` unchanged. `autobuild evidence`
   verified both manifests and the handoff hash.

### C. Rollover failure fails closed

Both used the same real Codex usage-limit failure:

| Fixture | Configuration | Result |
| --- | --- | --- |
| `live-06-rollover-unavailable` | replacement Claude with a non-existent executable | Preflight warned; run HUMAN_BLOCKED "no configured replacement implementer is available"; handoff kept; no commit; refs at base `aeaa119196a7` |
| `live-06-rollover-unsupported` | rollover list names only Codex | HUMAN_BLOCKED "unsupported provider transition: codex cannot replace itself after a provider-wide quota_exhausted"; no commit; refs at base `06f7a033b0e1` |

### Found live and fixed

- The A run's Claude implementer reported that the prompt showed the argv check
  `grep -qx "Autobuild 0.2 verification" …` without quotes (0.5 joined argv with
  spaces). The prompt now uses shell quoting; the controller always ran the
  correct argv.
- Blocked-rollover reports said "Files changed: not captured"; they now show the
  handoff snapshot. A Codex run with no final message is now reported as "no
  final message" instead of a schema error about `None`.

## Limitations

- Classification depends on CLI error text checked against real samples. A new
  message becomes `unknown` and stops for a human (safe, but no rollover).
- No automatic retry: transient errors stop recoverable for same-session resume.
- Reviewer rollover is not implemented; reviewers are configured explicitly.
- `max_rollovers` is capped at 1. A replacement starts cold and sees whatever
  the failed implementer left in the worktree, including its mistakes.
- Claude usage-limit and context-exhaustion messages could not be produced
  live; their patterns follow known Claude Code wording and are unit-tested only.
