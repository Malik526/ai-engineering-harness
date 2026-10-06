# Autobuild 0.6 Evaluation

Evaluation date: 2026-10-05 (America/New_York; run timestamps are UTC). This
record evaluates reviewer portability and bounded implementer rollover.
Providers: Claude Code 2.1.289 (2.1.290 after an automatic update before the
final runs), Codex CLI 0.160.0. Codex was out of quota between the first and the
final runs; Codex-dependent scenarios ran once it was available, with no
provider substitution.

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

### A. Reviewer matrix (Claude defect fixed, both reviewers live)

Every pairing ran the standard V-1 fixture with confined validation PASS, one
review cycle and a checkpoint on the run branch only; each fixture's `main`
stayed at its base.

| Fixture | Implementer → reviewer | Reviewer session | Result |
| --- | --- | --- | --- |
| `live-06-claude-review` | Claude → Claude | `4e06dea6…` | PASS; checkpoint `538d1ac301f3`; `main` `f0a9c33029b0` |
| `live-06-claude-impl-codex-review` | Claude → Codex | `01a10ea4-9633…` | PASS; checkpoint `f9d9eafcbe5e`; `main` `fd84a3de17eb` |
| `live-06-codex-impl-claude-review` | Codex → Claude | `3cc0acf3…` | PASS; checkpoint `24a4f3af6650`; `main` `9d4cc5067cba` |
| `live-06-codex-codex` | Codex → Codex | `01a10ea4-e4a8…` (implementer `01a10ea4-71d8…`) | PASS; checkpoint `4063f6913ca2`; `main` `81b2c44312dd` |

Both reviewers' raw answers normalized to the identical canonical key set
(Codex's wire-required null `blocked_reason` was omitted), with controller
identity and time. REVISE from a live reviewer is shown in B2 below; REVISE and
BLOCK normalization for both adapters is covered by unit tests.

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

### B2. Rollover during an open revision (induced session loss)

`live-06-rollover-session-loss` (browser counter fixture, two-attempt review
protocol), implementer Codex, reviewer Claude, rollover `max 1, automatic,
[claude]`. To lose a session safely, the fixture's Codex command was a wrapper
(kept in the fixture's `.git/`) that passes every call to the real Codex CLI
unchanged, except that `exec … resume <id>` names an unknown thread. Codex itself
then reported the lost session.

1. Codex session `01a10ea4-71dd…` built the counter with the handler unwired
   (protocol). Validation PASS; the real Playwright gate FAIL; fresh Claude
   reviewer `5ca53def…` returned REVISE with blocker R1-1 ("Clicking Increment
   changes the visible count from 0 to 1").
2. Same-session resume of Codex failed with Codex's own error `thread/resume
   failed: no rollout found for thread id …`, classified `session_unavailable`.
3. Handoff `rollover/rollover-01/handoff.json`: failed attempt 2, review cycle 1,
   rollover count 0/1, the Codex snapshot `44816e4a1939…` with `index.html`,
   protected `main` `221bf7427c0b`, brief/config hashes, hashed attempt-1
   validation (PASS), browser (FAIL) and review (REVISE), and the pending REVISE
   review as an open finding.
4. Claude session `812bce9c…` started as a new session ("You are a NEW
   implementer session … none of its memory") with the full brief, the handoff
   and R1-1. It kept Codex's markup and only wired the handler (8 lines added,
   1 changed).
5. Fresh evidence for attempt 3 on new snapshot `8746fe48eec7…`: confined
   validation PASS, Playwright PASS (screenshot shows count 1), fresh Claude
   reviewer `f13585a5…` PASS linked to `validation/cycle-03` and
   `browser/cycle-03`. Attempt-1 evidence stayed as history.
6. Checkpoint `efff14bbb41f` with `Autobuild-Implementer: claude` and
   `Autobuild-Rollover: codex -> claude (session_unavailable)`; `main` unchanged.
   `revision_history` shows initial (Codex) → resume (Codex, failed) → rollover
   (Claude), and `autobuild evidence` verified all four manifests and the handoff.

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
- B2's session loss was induced (unknown thread id through a wrapper), not a
  natural expiry; the error text and every controller step were real.
- `approval: human` and the resume re-decision path are covered by unit tests,
  not a live run.

## Status

0.6 is complete: both reviewers work in all four pairings, and rollover was
proven live after a real quota failure (B) and during an open revision with
partial work and an open finding (B2), with fail-closed behavior for an
unavailable replacement and an unsupported transition (C). After every run no
validation/browser process or temporary root remained, and no fixture `main`
moved.
