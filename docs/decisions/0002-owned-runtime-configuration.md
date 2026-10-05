# 0002 - Owned Runtime Configuration

**Status:** Accepted, 2026-10-04

## Context

The manual commit guards depended on edits to untracked runtime configuration.
A fresh clone could reproduce policy links but lacked the actual approval
mechanisms. Runtime configuration also holds unrelated user preferences and
may reference credentials; tracking whole configuration files is inappropriate.

## Decision

Track narrowly scoped definitions under `runtime/`: Claude's JSON guard fragment,
Codex's prompt rules, and policy-reference adapter fragments. Keep behavioral
policy in `policies/global/`. Codex's adapter reinforces only the canonical
completion format by reference.

The installer and audit share one reconciliation implementation. Detect providers
by executable availability; missing providers are skipped, including their skill
links. Core policy and shared skill links do not depend on either provider.

Markdown and rules use explicit begin/end ownership markers. Claude's command
hook has an ownership comment in its command string, using valid provider
configuration fields. The required ask rule is an additive set member. Preserve
other settings, rules, adapter routing, and hooks; reconcile stale marked content
and refuse ambiguous markers or conflicting user settings. Legacy unmarked
canonical hooks remain user-owned and are preserved.

Preflight all runtime files for each provider before changing that provider.
Writes are atomic per file and reject detected concurrent changes; the overall
installation is not transactional across files or providers. Another provider
and core links can still install when one provider conflicts. Never interpret
arbitrary user Starlark during setup: audit literal `prefix_rule` calls and
report advanced programs for manual inspection.

## Consequences

- A clone and installer reproduce guards for Claude-only, Codex-only, both, or
  neither installation, without authentication or provider API calls.
- Runtime settings remain outside Git; only the owned definitions are tracked.
- Moving the harness makes marked hook commands stale and safely repairable.
- Native approval remains available for explicitly requested manual commits.
- The Claude hook can inspect visible aliases and shell scripts. Prefix rules
  cannot resolve aliases or arbitrary executable code, and completion formatting
  remains model compliance. Audits establish configuration, not universal
  process control or guaranteed policy loading by every session.
- Autobuild retains its existing controller-owned checkpoint architecture.
