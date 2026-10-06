"""Autobuild: the deterministic control plane for planner / implementer / reviewer agent runs.

Subpackages are grouped by responsibility:
  core/          run lifecycle: preflight, runner, run store and states, resume, config, report
  policy/        autonomy gate, safety policy, secret detection, brief checks
  providers/     provider-neutral agent invocation; concrete CLIs only in providers/adapters/
  rollover/      bounded implementer rollover and handoff
  git/           worktree/branch isolation, snapshots, git guard, checkpoint decision
  validation/    confined normal validation and browser gates (shared sandbox)
  review/        canonical reviewer contract and prompts
  governance/    budgets, accounting, canonical stop reasons
  control/       remote stop
  notifications/ operator notifications
  common/        shared paths, YAML, schemas, front matter
cli.py, __main__.py and fixtures.py are the command-line entry points.
See ../README.md and docs/README.md.
"""

__version__ = "0.1.0"
