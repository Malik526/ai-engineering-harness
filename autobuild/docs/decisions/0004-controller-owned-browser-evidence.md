# ADR 0004: Controller-Owned Browser Evidence

Date: 2026-10-04
Status: Accepted

## Context

0.3 established independent semantic review and revisions but browser-required
briefs could checkpoint validated GREEN work before a manual browser gate. Agent
claims cannot establish browser execution, exit status or snapshot attribution.
Browser commands also introduce servers, artifacts and filesystem/network risks.

## Decision

Extend validation config with small explicit argv browser/e2e gates. The
controller runs each gate in mandatory Linux Bubblewrap isolation, owns service
readiness/cleanup and derives deterministic outcomes. Framework-produced JSON is
an artifact, not gate truth. Existing project browser tooling remains responsible
for assertions and screenshots/traces; no browser framework is invented.

Persist exclusive per-attempt evidence with snapshot/HEAD/run/review/brief/config
identity and file hashes. Fresh review consumes it before implementer narrative;
REVISE reruns gates after resumed implementation. Required FAIL/ERROR/SKIPPED or
missing brief-required coverage blocks checkpoint regardless of reviewer PASS.
This supersedes ADR 0003's inherited browser checkpoint/manual-gate exception.

Preserved hashes/identity are checked before agents, review and checkpoint,
including explicit resume. No stale evidence reuse, inference, provider fallback,
rollover, merge/push, remote browser infrastructure or production deployment.

## Consequences

The mechanical browser truth and semantic review remain complementary. Legacy
configs without browser requirements retain 0.3 flow; missing browser coverage
now requires configuration in a new run rather than an uncertified checkpoint.
Tests must place reports/caches in approved fresh output/private temp paths, and
dependencies must be prepared before the read-only gate. Unsupported platforms
or denied namespace permissions fail closed. Normal validation/provider gaps,
readable system assets, trusted-test assumptions and lack of content scanning/
resource quotas remain explicit. Highest-value follow-up: apply equivalent
confinement to normal validation before expanding autonomous job scope.
