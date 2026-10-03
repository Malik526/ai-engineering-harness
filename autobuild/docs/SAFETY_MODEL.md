# Safety Model

## Invariant

**Autonomous agents never modify a protected branch.** Protected branches are
listed per project in `git.protected_branches`, initially `main`. All
autonomous work happens on a branch under `git.branch_prefix`, inside a
dedicated worktree. Config validation rejects a prefix that could produce a
protected branch name, and run-state validation rejects a run whose branch is
protected.

## Trust Boundaries

| Boundary | Trusted to | Not trusted to |
| --- | --- | --- |
| Human | Approve plans, merge, handle secrets and accounts, deploy | — |
| Controller (deterministic code) | Enforce policy, isolate work, stop, notify | Make product or architecture judgments |
| Planner | Propose and classify work | Mark its own plan approved |
| Implementer | Edit its assigned worktree | Approve its work; touch anything outside its worktree |
| Reviewer | Judge evidence | Edit code; trust the implementer's narrative |

## Operations

Operation ids live in `policy/safety.yaml`, and `autobuild/safety.py` checks
them. The policy is **default-deny**: an id missing from `allowed` is refused.

Allowed:

- `repo_read`: read the repository
- `worktree_edit`: edit files inside the assigned worktree
- `run_tests`: run the project's test, lint, typecheck and build commands
- `run_dev_server`: run a local development server
- `browser_automation`: drive a browser against local servers
- `docs_update`: update project documentation and changelog
- `commit_to_assigned_branch`: commit on the run's own branch
- `create_child_branch`: branch a dependent item from a reviewed predecessor

Prohibited:

- `merge_protected_branch`: merge into a protected branch
- `push_protected_branch`: push to a protected branch
- `commit_protected_branch`: commit on a protected branch
- `force_push`: force-push any branch
- `delete_remote_branch`: delete remote branches
- `production_deploy`: deploy to production
- `production_db_destructive`: destructive production database operations
- `secret_disclosure`: print, log or transmit secrets
- `filesystem_outside_scope`: read or write outside the approved paths
- `external_purchase`: buy services
- `billing_change`: change billing
- `account_creation`: create external accounts

## Enforcement Layers

The policy files describe intent. They don't confine a running agent on their
own. Real enforcement is layered, so no single layer depends on a model
cooperating.

1. **Policy (0.1, this phase).** The schemas, `policy/*.yaml` and validators reject unsafe configuration and state.
2. **Agent confinement (0.2).** The controller runs agents non-interactively inside the worktree, with tool allow/deny lists, a pre-tool hook that refuses protected-branch, merge, force-push and out-of-scope commands, sandboxing where the provider supports it, and turn limits.
3. **Controller checks (0.2+).** Before and after each run, the controller compares the tips of the protected branches. Any change fails the run and is reported as `protected_branches.modified: true`.
4. **Server-side backstop (human action, recommended now).** Turn on GitHub branch protection for `main` in every project autobuild drives: no direct pushes, no force pushes.
5. **Out-of-band stop.** See `CONTROL_CONTRACT.md`. Stopping never depends on an agent.

## Secrets

Agents never receive secrets through briefs, artifacts or notifications. When
an item needs a new credential it is YELLOW, and the human adds the secret
through the project's approved mechanism. Run directories are git-ignored.
