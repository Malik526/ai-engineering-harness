# 0001 - Policy Intent Plus Deterministic Enforcement

**Status:** Accepted, 2026-10-04

## Context

The global policy layer is the vendor-neutral source of truth for engineering
behavior across Claude Code, Codex, and future local agents. Some rules need
engineering judgment and belong in Markdown instructions. Other rules are
mechanical enough that relying only on model compliance is weaker than the
harness needs.

The harness also has two operating contexts:

- **Always-on manual development:** normal interactive agent work, governed by
  global policies and runtime capabilities.
- **Autobuild:** explicitly invoked autonomous runs with controller-owned
  state, worktrees, validation, and checkpoint commits.

The audit needed to harden deterministic rules without turning normal manual
development into Autobuild or duplicating vendor/runtime protections.

## Decision

Use a three-layer enforcement model:

1. **Policy as intent:** `policies/global/*.md` defines portable engineering
   expectations and judgment-heavy rules.
2. **Deterministic mechanisms where reliable:** hooks, runtime permission
   prompts, Codex execpolicy rules, schemas, audit scripts, Git wrappers,
   workspace boundaries, and validation commands enforce mechanical rules.
3. **Explicit reconciliation:** documentation artifacts identify what is
   enforced, what is hybrid, and what remains semantic.

`docs/POLICY_ENFORCEMENT_MATRIX.md` is the authoritative audit artifact for
this classification. `scripts/setup/audit_instructions.py` must remain a
read-only wiring audit and now verifies that the matrix covers every
canonical global policy.

Autobuild-specific controls stay inside Autobuild. Normal manual development
may reuse runtime-level safety mechanisms, such as commit prompts, but it must
not inherit Autobuild's autonomous checkpoint behavior unless Autobuild is
explicitly invoked.

## Consequences

- Global policies remain human-readable and vendor-neutral.
- Deterministic controls are added only where they improve reliability without
  making legitimate work harder.
- Semantic rules such as "read the relevant context", "decide whether an ADR
  is warranted", and "choose verification depth" stay model-judgment rules.
- Future hardening work should update the matrix first, then add narrow code
  only when the enforcement value is clear.
