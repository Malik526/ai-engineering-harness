# Policy Enforcement Evaluation

**Date:** 2026-10-04
**Scope:** Global policy layer, runtime adapters, runtime commit guards, and
Autobuild deterministic controls.

## Questions Evaluated

1. Do Claude Code and Codex both receive the canonical global policies?
2. Do deterministic controls still work when an agent would otherwise run a
   disallowed manual commit?
3. Does normal manual development remain distinct from Autobuild?
4. Does Autobuild checkpoint behavior remain controller-owned and isolated to
   run branches?
5. Are new enforcement artifacts wired into read-only audits and tests?
6. Are semantic rules left as instructions instead of brittle automation?

## Evidence

| Check | Mechanism | Expected result | Result |
| --- | --- | --- | --- |
| Global policy loading | `scripts/setup/audit_instructions.py` | Every file in `policies/global/` is symlinked to `~/.agents/` and referenced by both runtime adapters. | Pass: audit reports all six policies loaded by both runtimes. |
| Policy matrix coverage | `scripts/setup/audit_instructions.py` and `scripts/tests/test_instruction_audit.py` | Missing matrix entries for canonical policies fail the audit/test. | Pass: audit covers the live matrix; unit test verifies a missing `SECURITY.md` entry fails. |
| Claude manual commit guard | `scripts/hooks/git_commit_guard.py` and `scripts/tests/test_git_commit_guard.py` | `git commit`, `git -C ... commit`, global-option forms, and multi-command forms ask; non-commit Git commands pass. | Pass: hook tests cover commit and non-commit forms. |
| Codex manual commit guard | `~/.codex/rules/default.rules`, audited by `audit_instructions.py` | `git commit`, `git -C`, and `git -c` prompt rather than silently running. | Pass: live audit confirms all three Codex prompt rules. |
| Autobuild checkpoint ownership | `autobuild/autobuild/git/checkpoint_policy.py`, runner tests | GREEN validated work checkpoints on run branch; disabled/non-GREEN/failed/no-change/protected cases do not. | Pass: Autobuild suite covers checkpoint policy and runner behavior. |
| Manual mode usability | Policy matrix review | No background service, global write hook, or mandatory Autobuild behavior was added to normal work. | Pass by design |
| Semantic rule preservation | Policy matrix review | Context relevance, documentation authority, verification depth, and architectural judgment remain model instructions. | Pass by design |

## Deliberate Violation Tests

- Missing a global policy from `docs/POLICY_ENFORCEMENT_MATRIX.md` must fail
  `audit_policy_matrix()`.
- Running the Claude hook with representative `git ... commit` shell forms
  must return a permission decision of `ask`.
- Autobuild tests simulate provider failure, validation failure, agent commits,
  protected-branch movement, secret-like files, and disabled checkpoint commits.

## Conclusion

The audit keeps always-on global policy separate from Autobuild-specific
controls. Low-risk deterministic backing is appropriate for instruction-chain
coverage, manual commit prompts, controller-owned checkpoints, run-state
schemas, and configured validation commands. Judgment-heavy rules remain in
Markdown policy and are listed in the enforcement matrix so they do not become
accidental automation targets.

Verification commands run:

- `/home/malik/ai-engineering-harness/autobuild/.venv/bin/python -m pytest scripts/tests` -> 18 passed.
- `python3 scripts/setup/audit_instructions.py` -> passed.
- `/home/malik/ai-engineering-harness/autobuild/.venv/bin/python -m pytest` from `autobuild/` -> 174 passed.

## 2026-10-04 - Runtime Portability Follow-Up

The local-only guard configuration above is superseded by versioned `runtime/`
definitions and installer/audit reconciliation. See
[Runtime Guard Evaluation](RUNTIME_GUARD_EVALUATION.md) for fresh-home cases,
measured Codex completion results, Claude validation, and remaining bypasses.
The original evidence remains historical; the current mechanism is described in
`RUNTIME_GUARDS.md` and the updated enforcement matrix.

## 2026-10-04 - Manual Completion Follow-Up

The previously recommended manual completion backing is now implemented as a
shared evidence check and adapter instruction. See
[Manual Completion Evaluation](MANUAL_COMPLETION_EVALUATION.md) for fixture
coverage, regression results and invocation/semantic limitations. The historical
results above remain unchanged; ADR 0003 records the current architecture.

## 2026-10-04 - Autobuild Independent Review Follow-Up

Autobuild 0.3 adds fresh read-only reviewers, bounded resumed corrections,
per-cycle evidence and explicit human resume without changing manual-mode
commit ownership. See [Autobuild 0.3 Evaluation](../autobuild/docs/evaluations/EVALUATION_0_3.md)
for fake-provider safety regressions and live Codex REVISE-to-PASS/resume results.
Fixture main remained unchanged. Live Claude-to-Codex completion is quota-blocked,
not a passing cross-provider result. The earlier evaluations remain historical.
