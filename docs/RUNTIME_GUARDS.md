# Runtime Guards

`policies/global/GIT.md` owns commit and completion behavior. `runtime/` contains
the provider-specific mechanisms that reinforce it:

| Definition | Installed location | Ownership |
| --- | --- | --- |
| `runtime/claude/settings.fragment.json` | `~/.claude/settings.json` | Additive ask rule; hook command ends with `# AI Engineering Harness: commit guard` |
| `runtime/claude/adapter.fragment.md` | `~/.claude/CLAUDE.md` | Markdown begin/end block |
| `runtime/codex/default.rules` | `~/.codex/rules/default.rules` | Comment begin/end block |
| `runtime/codex/adapter.fragment.md` | `~/.codex/AGENTS.md` | Markdown begin/end block |

The installer renders the Claude hook's `{commit_hook}` placeholder as a
shell-quoted absolute path to this checkout. Fragments contain no authentication,
personal preferences, MCP configuration, or project routing. Existing content
outside owned blocks remains user-owned. Existing unmarked canonical hooks and
rules are preserved; migration may leave equivalent duplicate guards.

## Reconciliation And Audit

`scripts/setup/install.py --check` and `audit_instructions.py` are read-only.
`install.py --apply` adds missing definitions and replaces stale marked content.
`--adopt` additionally adopts identical policy/skill copies using the existing
backup flow. Conflicts stop runtime writes for that provider; core links and
other providers still proceed. A failed operation returns nonzero. Updates name
the file and owned section changed. Writes preserve existing file modes and JSON
values outside the owned settings, though JSON whitespace is reformatted.

Provider detection uses `PATH`. The real-home installation honors `CODEX_HOME`
and `CLAUDE_CONFIG_DIR`; `--home /isolated/home` ignores these overrides for
reproducible simulations. Neither provider is required. Installing a provider
later requires rerunning setup. Installer/audit operations never start a model
session or read authentication files.

| Audit status | Meaning |
| --- | --- |
| `PASS` | Required owned content matches canonical definitions |
| `MISSING` | A required section, setting, adapter, or policy link is absent |
| `STALE` | A marked section, hook command, or adapter reference drifted |
| `CONFLICT` | User configuration conflicts, is malformed, uses ambiguous ownership, or cannot be reconciled safely |
| `SKIP` | Provider executable is absent |

Claude checks the ask rule, exact canonical hook command/type/timeout/matcher,
user-hook disablement, incompatible default permission modes, and representative
overlapping allow/deny permissions.
An unmarked hook pointing to a different checkout conflicts. Codex checks exact
owned rules and adapter content, conflicting forbidden prefixes in all user
`rules/*.rules`, and a nonempty `AGENTS.override.md` that supersedes the adapter.
Advanced Starlark and symlink configuration files require manual reconciliation.
Codex's restrictive decision precedence means an overlapping `allow` cannot
override the managed `prompt`; `forbidden` is flagged because it blocks approved
commits. These checks inspect user configuration, not every project, enterprise,
CLI override, or provider runtime setting.

## Guard Coverage

The Claude hook recognizes direct commits, Git global options, common command
wrappers, shell `-c` strings, inline shell-alias definitions, Git aliases resolved
through Git's config parser (including inline `-c`, repository `-C`, and visible
environment assignments), and explicit small shell scripts. Alias lookup is
read-only, bounded to one second per lookup, and never executes the alias.
Script inspection is limited to explicit paths/shell arguments, shell shebangs
or `.sh` files, 64 KiB, and six recursion levels. It does not intercept subprocesses.

Codex rules cover `git`, `/usr/bin/git`, and `/bin/git` with `commit` and selected
separate global-option tokens. Options prompt conservatively even for reads.
The native engine verifies the definitions:

```bash
codex execpolicy check --rules runtime/codex/default.rules git -C /repo commit
codex execpolicy check --rules runtime/codex/default.rules /usr/bin/git commit
```

Both must report `prompt`. An explicit human commit request proceeds through
provider approval; unattended sessions cannot supply that approval. The harness
does not replace prompts with permanent commit denial.

## Limits And Live Evaluation

Persistent shell aliases/functions unavailable to the hook, dynamic expansion,
opaque/binary/Python wrappers, generated scripts, very large scripts, arbitrary
Git executables, `GIT_EXEC_PATH` helpers, and indirect mechanisms such as
`commit-tree` are outside coverage. Codex prefixes also miss attached option
tokens such as `--git-dir=.git`, unknown Git aliases and arbitrary wrappers.
Advanced shell parsing, ignored rules, disabled hooks, and permission-bypass
launch modes weaken these controls. Static inspection can conservatively prompt
for code in an unused branch. The guards are defense in depth, not a sandbox.

The completion reminder is an instruction, not a deterministic final-message
gate. No final-message hook is introduced by this change. Measure its behavior
with multiple manual fixtures and retain the sample size and failures.

```bash
autobuild/.venv/bin/python scripts/evaluations/runtime_guard_fixtures.py --provider codex --runs 3
autobuild/.venv/bin/python scripts/evaluations/runtime_guard_fixtures.py --provider claude --runs 1
autobuild/.venv/bin/python scripts/evaluations/runtime_guard_fixtures.py --provider codex --case explicit --runs 1
autobuild/.venv/bin/python scripts/evaluations/runtime_guard_fixtures.py --provider claude --case explicit --runs 1
```

The existing fixture factory supplies disposable baseline repositories under
`autobuild/.test-runtime/`. Sessions operate manually; no Autobuild run is
started. Logs, final messages and measured results stay in each fixture's
`.git/harness-evaluation/`. The harness repository is never committed by the
evaluation. Remove owned fixtures through `autobuild fixture clean` after review.
See `RUNTIME_GUARD_EVALUATION.md` for measured results and ADR 0002 for ownership.

Provider references: [OpenAI rules documentation](https://learn.chatgpt.com/docs/agent-configuration/rules),
[Claude hook reference](https://code.claude.com/docs/en/hooks),
and [Claude permissions](https://code.claude.com/docs/en/permissions).
