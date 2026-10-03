# Universal Security Policy

This file is the vendor-neutral source of truth for security standards that apply across Claude Code, Codex, and any future local AI agent.

## Secrets And Credentials

- Never commit credential files, private keys, tokens, API secrets, database dumps, or `.env` files containing secrets.
- Protect environment files with `.gitignore` before working with credential-backed code.
- Do not duplicate secrets into project directories, docs, test fixtures, generated files, screenshots, or logs.
- Reference existing credential files from their approved location instead of copying them.
- Never expose server-only credentials to client-side code, public build output, or browser-accessible environment variables.

## Before Commit Or Publish

- Check staged files for accidental secrets before committing.
- Keep sample environment files free of real secrets.
- Use placeholders in documentation and examples.
- Do not weaken existing secret protections, authentication checks, authorization rules, or data-access boundaries unless the user explicitly asks and the security impact is clear.

## External Services

- Treat service-account files, OAuth credentials, deployment tokens, and database URLs as sensitive.
- Avoid printing secrets in terminal output or final responses.
- If verification requires credentials that are unavailable or unsafe to use, state that verification could not be performed safely.
