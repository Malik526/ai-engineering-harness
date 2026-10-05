# Policy Enforcement Matrix

**Status:** Authoritative audit, 2026-10-04

This matrix classifies the meaningful rules in the global policy layer and
records which parts should remain model judgment, which parts are enforced
deterministically, and where hybrid backing is useful. The canonical policy
source remains `policies/global/`.

Classification:

- **Semantic:** needs engineering judgment and stays primarily instructional.
- **Deterministic:** can be enforced reliably with code, configuration,
  schemas, hooks, sandboxing, or Git controls.
- **Hybrid:** needs model judgment but benefits from deterministic checks.

Implementation status:

- **Implemented:** deterministic support exists and is tested or audited.
- **Partial:** some deterministic support exists, but judgment or follow-up is
  still required.
- **Instruction only:** intentionally remains a model instruction.
- **Recommended:** useful future hardening, not implemented here.

| Policy source | Rule | Classification | Current enforcement mechanism | Enforcement gap | Recommended mechanism | Implementation status |
| --- | --- | --- | --- | --- | --- | --- |
| `policies/global/CODING.md` | Apply global coding standards unless a project-local instruction is stricter. | Hybrid | Runtime adapters load `~/.agents/*.md`; `audit_instructions.py` verifies adapter and symlink coverage. | Agents can still overlook project-local instructions without a project-specific audit. | Keep instruction; add project-local policy checks only inside projects that need them. | Partial |
| `policies/global/CODING.md` | Prefer smallest relevant context before changing code. | Semantic | Policy instruction. | Relevance is task-specific and cannot be reliably inferred from file counts. | Keep as judgment rule. | Instruction only |
| `policies/global/CODING.md` | Keep reusable components/utilities/hooks in their own files when the project structure supports it. | Semantic | Policy instruction and code review. | Repository conventions vary; deterministic file-count rules would be noisy. | Keep as judgment rule; use project lint rules where a project has a fixed component architecture. | Instruction only |
| `policies/global/CODING.md` | Use TypeScript for new frontend files in TypeScript frontend projects. | Hybrid | Policy instruction; project type checks catch many violations. | Harness cannot know every project's frontend conventions. | Reuse project `tsc`/lint validation instead of adding global file heuristics. | Partial |
| `policies/global/CODING.md` | Preserve existing patterns and public behavior unless explicitly changed. | Semantic | Policy instruction and tests. | Requires understanding intent and behavior. | Keep as judgment rule, backed by project tests. | Instruction only |
| `policies/global/DOCUMENTATION.md` | Load only relevant project/module context and avoid unrelated project histories. | Semantic | Policy instruction. | Relevance is task-specific. | Keep as judgment rule. | Instruction only |
| `policies/global/DOCUMENTATION.md` | Keep project-specific knowledge out of global policy and skills. | Hybrid | Policy instruction; `audit_instructions.py` flags pasted auto-memory markers. | No general detector for all project-specific facts. | Add targeted detectors only for recurring drift patterns. | Partial |
| `policies/global/DOCUMENTATION.md` | Add useful comments for non-obvious new code, not empty narration. | Semantic | Policy instruction and review. | Comment usefulness is contextual. | Keep as judgment rule. | Instruction only |
| `policies/global/DOCUMENTATION.md` | Reconcile changed authoritative facts across changelog, project state, evaluations, ADRs, and docs before completion. | Hybrid | Policy instruction plus shared manual reconciliation evidence (six documentation areas). | Shared manual check requires six fresh documentation decisions and changed paths for claimed updates; conceptual correctness remains semantic. | Keep shared evidence check and adapter invocation; see MANUAL_COMPLETION_EVALUATION.md. | Partial: manual evidence check implemented |
| `policies/global/DOCUMENTATION.md` | Record meaningful changes in the canonical changelog. | Hybrid | Policy instruction; changelog review during completion. | No global detector that a meaningful change lacks changelog coverage. | Prefer project-specific tests or PR checks for repositories where changelog discipline is critical. | Recommended |
| `policies/global/EXECUTION.md` | Follow the repo's policy/docs hierarchy before implementing. | Hybrid | Policy instruction; `audit_instructions.py` verifies the global policy/adaptor chain. | It cannot prove the agent read the right project docs. | Keep as instruction; use project-specific doc-consistency tests where possible. | Partial |
| `policies/global/EXECUTION.md` | Execute directly from the brief unless a genuine architectural conflict requires planning. | Semantic | Policy instruction. | Requires judgment about ambiguity and risk. | Keep as judgment rule. | Instruction only |
| `policies/global/EXECUTION.md` | Do not scan the entire repository or unrelated docs by default. | Semantic | Policy instruction. | A deterministic read budget would hurt legitimate debugging. | Keep as judgment rule. | Instruction only |
| `policies/global/EXECUTION.md` | Manual `report` ends with a completion summary and recommended commit when applicable, without an automatic commit. | Hybrid | `GIT.md`; minimal Codex adapter reminder; owned runtime guards; manual fixture evaluation. | Manual check returns commit_recommendation_required; final-message formatting remains model compliance. | Retain the measured sample and rerun completion fixtures after runtime changes. | Partial: measured in `RUNTIME_GUARD_EVALUATION.md` |
| `policies/global/GIT.md` | Manual development never runs `git commit` unless the human explicitly asks for this change. | Hybrid | Versioned `runtime/` fragments; Claude ask rule and alias/script-aware hook; Codex native prompt rules; shared setup/audit reconciliation. | Opaque subprocesses, unknown aliases in Codex, and deliberate override modes remain outside coverage; selected option prefixes also prompt on reads. | Preserve layered approval and document bypasses; keep stronger controller enforcement inside Autobuild. | Implemented for documented command forms; remaining process-level gaps |
| `policies/global/GIT.md` | Autobuild agents never commit; controller checkpoint commits only when policy allows it. | Deterministic | Autobuild git shim and `checkpoint_policy.py`; controller state records checkpoint decision; runner tests. | Applies only inside Autobuild runs. | Keep Autobuild-only; do not force normal manual work into Autobuild semantics. | Implemented |
| `policies/global/GIT.md` | Never merge into protected branches, push, force-push, or rewrite shared history without explicit human instruction. | Hybrid | Policy instruction; Autobuild protected-branch checks, git shim, `GitClient`, safety policy, tests. | Normal manual mode relies on runtime approvals and model compliance. | Add optional local hooks only if they can avoid blocking legitimate human Git work. | Partial |
| `policies/global/GIT.md` | Preserve unrelated dirty worktree changes and do not stage unrelated files. | Semantic | Policy instruction; final diff review. | Requires identifying task ownership. | Keep as judgment rule. | Instruction only |
| `policies/global/GIT.md` | Do not include credentials or unrelated local changes in commits. | Hybrid | Security policy; Autobuild secret-like file guard; manual pre-commit instruction. | Manual completion reuses the existing secret-like filename guard; no content scanner. | Reuse project secret scanners or Git hooks where already configured. | Partial |
| `policies/global/SECURITY.md` | Never commit credentials, private keys, tokens, database dumps, or secret `.env` files. | Hybrid | Shared secret-like filename guard reused by Autobuild and manual completion. | Manual completion reuses filename guard; content/ignored-file coverage remains a gap. | Prefer existing tools such as project pre-commit secret scanners; avoid custom brittle regex-only scanners. | Partial |
| `policies/global/SECURITY.md` | Keep server-only credentials out of client-side/public output. | Semantic | Policy instruction; project tests/build checks when available. | Requires project architecture knowledge. | Keep as judgment rule, backed by framework-specific checks in projects. | Instruction only |
| `policies/global/SECURITY.md` | Do not weaken authentication, authorization, or data boundaries unless explicitly requested and impact is clear. | Semantic | Policy instruction and review. | Requires security judgment. | Keep as judgment rule. | Instruction only |
| `policies/global/SECURITY.md` | Avoid printing secrets in terminal output, docs, fixtures, screenshots, or final responses. | Hybrid | Policy instruction; no broad log scanner. | Universal scanning risks false positives and leaked-match reporting. | Use targeted scanners in sensitive repos and redact findings. | Recommended |
| `policies/global/VERIFICATION.md` | Run applicable tests, type checks, lint, formatting, build validation, and local execution when safe. | Hybrid | Autobuild configured validation; manual completion reuses runner/schema with fresh result evidence. | Manual check runs selected existing commands, verifies fresh results and requires test/typecheck/lint/build/runtime decisions; selection remains semantic. | Reuse project scripts; consider a per-project validation manifest where reliability matters. | Partial |
| `policies/global/VERIFICATION.md` | Report verification commands and explain skipped checks. | Semantic | Policy instruction. | Depends on the completed work and available commands. | Keep as judgment rule; structured reports could help in Autobuild. | Instruction only |
| `policies/global/VERIFICATION.md` | Match verification depth to risk and blast radius. | Semantic | Policy instruction. | Risk assessment is judgment-based. | Keep as judgment rule. | Instruction only |
| `policies/global/VERIFICATION.md` | Completion verification includes documentation/changelog reconciliation. | Hybrid | Documentation policy plus fingerprint-bound manual reconciliation check. | Manual evidence gate verifies reconciliation presence/freshness; invocation is adapter instruction. | Shared manual completion check; semantic decisions remain agent-owned. | Partial: manual evidence check implemented |

## Vendor Capability Reuse

| Capability | Reused for | Notes |
| --- | --- | --- |
| Claude Code PreToolUse hooks | Manual-mode `git commit` guard | The hook asks on direct commits, visible Git aliases, shell `-c`, inline shell alias definitions, and small explicit shell scripts. |
| Claude Code permissions | Human approval for manual commits | `audit_instructions.py` rejects silent allow rules and requires an ask rule. |
| Codex execpolicy prompt rules | Manual-mode commit prompt | Canonical `runtime/codex/default.rules` is reconciled into a marked local section; covers direct commits, selected separate options and standard absolute Git paths. |
| Runtime fragment reconciliation | Fresh-machine portability and drift detection | Installer/audit share ownership-aware merges; providers are optional; unrelated settings are preserved; conflicts are refused. |
| Codex sandbox / workspace-write model | Filesystem boundary for normal Codex work | Reused as a runtime capability; the harness does not duplicate it. |
| Autobuild git shim and `GitClient` | Agent read-only Git and protected-branch controls in Autobuild | Kept Autobuild-specific so manual development stays usable. |
| JSON Schemas | Autobuild run state, configs, reviews, validation artifacts | Existing schema validation remains the right deterministic mechanism for structured artifacts. |
| Project validation commands | Tests/lint/build/type checks where configured | Existing project commands are preferred over global inference. |

## Deterministic Gaps To Keep Visible

- Manual completion checks fresh reconciliation records, not conceptual
  correctness. Invocation is prompted by both adapters; no final-message hook
  guarantees the agent invokes it. Documentation authority remains semantic.
- Manual mode has no universal secret scanner. Reuse project scanners where
  available; avoid a global regex scanner that trains agents to dump suspected
  secrets into logs.
- No runtime-neutral mechanism proves that an agent loaded only relevant
  context. That should remain a semantic policy.
- Codex's current prompt rules for `git -C` and `git -c` are conservative and
  may prompt for non-commit commands. They are acceptable because they fail
  safe, but vendor-native shell-command hooks would be cleaner if exposed.
- Guard coverage is bounded. Arbitrary executable code, hidden aliases, indirect
  commit mechanisms and launch overrides are documented in `RUNTIME_GUARDS.md`.
  Completion formatting has a vendor reminder and measured results, but no
  deterministic final-message gate.

## Manual Completion Backing (2026-10-04)

`scripts/manual/complete.py` provides deterministic Git status (staged/unstaged,
untracked, conflicts and in-progress operations), changed-file acknowledgements,
validation command status/freshness, filename safety and Autobuild exclusion.
Six documentation areas and five validation categories use explicit semantic
applicability decisions; claimed documentation updates require changed paths.
The returned recommendation flag reinforces GIT.md without copying commit policy.
Both adapters share the same instruction and script; invocation and actual final
reply formatting remain model compliance. No automatic commit or repair loop.
See [fixture evaluation](MANUAL_COMPLETION_EVALUATION.md) and ADR 0003.
