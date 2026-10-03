<!--
runs/<run-id>/review/review-NN.md — reviewer narrative for one cycle.
The decision lives in review-NN.json (review.schema.json); this file explains it.
Review against evidence in this order: brief, git diff, changed files,
validation output, browser evidence, ADRs/project state. Read the
implementer's summary last and do not accept its claims without evidence.
-->
# Review <NN> — <implementation id>

**Status:** PASS | REVISE | BLOCKED

## Evidence Examined

- Brief (sha256 matches state.json): yes/no
- Diff: `implementation/diff.patch`
- Validation: `implementation/validation.json` (producer: controller/implementer)
- Browser evidence: present / not required / missing

## Findings

### R<NN>-1 — <severity>

- **Requirement:** brief section or acceptance item
- **Evidence:** file:line, test output, or screenshot
- **Affected files:** ...
- **Required correction:** ...

## Blocked Reason

BLOCKED only: what the human must decide or provide.
