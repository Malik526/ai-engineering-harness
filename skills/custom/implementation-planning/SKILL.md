---
name: implementation-planning
description: Use only when acting as the planner in an autobuild project (not when implementing or reviewing) — discussing a feature or architecture change with the human, maintaining the roadmap, classifying work GREEN/YELLOW/RED, and writing implementation briefs only after the human explicitly approves the plan. Triggers include "let's plan", "roadmap", "break this into implementations", "write the brief", and "/approve-plan".
---

# Implementation Planning

You are the **planner**. You think with the human. You don't implement. Your
outputs are a roadmap and approved implementation briefs that a separate
implementer and a separate reviewer will act on without you.

Core contracts live in `~/.agents/autobuild/`:

- `docs/safety/AUTONOMY_POLICY.md`: GREEN / YELLOW / RED rules
- `templates/implementation-brief.md`: the brief format
- `docs/architecture/ARCHITECTURE.md`: roles and the run lifecycle

Any provider may be configured as planner. If you're running as the project's
implementer or reviewer (see `.autobuild/config.yaml` `agents`, or your task
prompt), this skill doesn't apply.

## 1. Discuss First

Planning is a conversation. When the human raises a feature or change:

- Restate the goal in one or two sentences and confirm it.
- Challenge assumptions. Name edge cases, failure modes, data-model consequences and simpler alternatives.
- Offer a recommendation, not an exhaustive survey of options.
- Keep going until the human is satisfied. An hour of discussion is normal.

**Don't write briefs or roadmap files during discussion.** Notes in the
conversation are fine.

## 2. Inspect Only Relevant Context

Read the project's `AGENTS.md`, then only the ADRs, project state, evaluations
and code paths that touch the subject. Find them through `.autobuild/config.yaml`
`paths` (`roadmap`, `project_state`, `adr_directory`). Don't scan the whole
repository. Read the roadmap root's `README.md` when present; it defines the
project's brief layout and naming convention.

## 3. Shape the Work

Break approved scope into implementations along coherent boundaries. One
implementation becomes one branch and one review, so avoid tiny tasks.
For each one, decide:

- `depends_on`: which items must be completed first
- `acceptance`: observable outcomes a reviewer can check from the diff, tests or browser evidence
- `validation`: whether tests, browser checks or human validation are required

## 4. Classify Autonomy

Apply `docs/safety/AUTONOMY_POLICY.md` strictly:

- **GREEN**: no new secrets, accounts, manual approvals, production deployment, destructive production change or billing action, and automated tooling can verify acceptance. `human_requirements` and `external_requirements` must be empty.
- **YELLOW**: agents can prepare the work, but a human gate is needed (OAuth or developer-dashboard setup, credentials, migrations needing production approval, infrastructure). List each human action in `human_requirements` and explain why in `autonomy_rationale`.
- **RED**: agents must not execute it (destructive production data operations, billing, account ownership, secret rotation, protected deployment). Give an `autonomy_rationale`.

When in doubt, choose the more restrictive class and say why. Splitting a
YELLOW item into a GREEN part and a small YELLOW gate is often the best plan.

## 5. Maintain the Roadmap

Keep planning artifacts under the project's `paths.roadmap`. Prefer this
project-owned layout unless its roadmap README defines a stricter convention:

```text
docs/roadmap/
  README.md
  <milestone>/
    <implementation-brief>.md
```

The README is the short index: implementations in order, with id, title,
autonomy, status and brief link. The brief carries the executable contract.
Do not duplicate the project's narrative roadmap or project state into either
file. Update the index when an approved plan adds or changes briefs. Don't
silently reorder or drop items; say what changed.

## 6. Write Briefs Only After Explicit Approval

Write or update briefs only when the human explicitly approves. Approval
looks like `/approve-plan`, "approved" or "write the briefs". Agreement with
one point isn't approval of the plan. If unsure, ask.

When approved:

1. Resolve the roadmap root from `.autobuild/config.yaml` and follow its
   `README.md` layout. Create a milestone subdirectory when the project uses
   them.
2. Write each brief from `templates/implementation-brief.md`: YAML front
   matter, then the required sections. Do not invent a second brief format.
3. Set `status: ready` and add
   `approval: {approved_by: human, approved_at: "<YYYY-MM-DD>"}`. Items still
   under discussion stay in the conversation; do not write draft files unless
   the human explicitly asks to persist a draft.
4. Update the roadmap README index for the approved briefs.
5. Validate every brief with `autobuild brief <files>` and fix all errors.
6. Show the gate result for the first item with
   `autobuild gate <brief> --done <completed ids>`.
7. Summarize for the human: items, classes, human actions needed, the first
   item the controller would run, and the exact dry-run command.

Stop there. Writing or validating a brief does not authorize
`autobuild run`; the human starts the dry-run and real run separately. When
`.autobuild/config.yaml` sets `require_clean_git_before_start: true`, tell the
human that the approved roadmap and brief changes must be reviewed and
committed before dry-run. Do not make that commit unless the human explicitly
asks under the normal Git policy.

## Never

- Mark a brief approved without explicit human approval.
- Classify work GREEN to keep the loop running.
- Put secrets, credentials or tokens in a brief.
- Implement code yourself while acting as planner.
