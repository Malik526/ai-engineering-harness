<!-- BEGIN AI Engineering Harness -->
## Shared Engineering Policy

Follow the canonical global policies before project-specific instructions:

- `~/.agents/CODING.md`
- `~/.agents/DOCUMENTATION.md`
- `~/.agents/EXECUTION.md`
- `~/.agents/GIT.md`
- `~/.agents/SECURITY.md`
- `~/.agents/VERIFICATION.md`

For manual-development completion, follow `~/.agents/GIT.md`, including its
final `Recommended commit:` line when applicable.

Before reporting manual work complete, follow `~/.agents/manual-completion/README.md`
and run `python3 ~/.agents/manual-completion/complete.py` with task-local evidence.
Resolve `NEEDS_ATTENTION` findings where authorized, then rerun the relevant check;
report blockers instead of normal success. This is one completion check, not an
autonomous repair loop. Autobuild owns its own completion and is excluded.
Use `~/.agents/GIT.md` for the final commit recommendation and commit authorization.
<!-- END AI Engineering Harness -->
