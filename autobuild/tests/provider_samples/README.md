# Provider error samples

Trimmed copies of real CLI output captured on 2026-10-05 and used by
`tests/test_reviewer_portability.py` to test failure classification:

- `codex-usage-limit.jsonl`: Codex CLI 0.160.0 `exec --json` after the account's
  usage limit was reached (top-level `error` and `turn.failed` events; config
  warning items removed).
- `codex-unknown-thread.stderr.txt`: Codex `exec resume <unknown id>` stderr.
- `claude-unknown-session.stderr.txt`: Claude Code 2.1.289 `-p --resume <unknown id>` stderr.
- `claude-schema-rejected.json`: Claude Code 2.1.289 result envelope when the
  unprojected review schema (top-level `allOf`) was sent with `--json-schema`.
