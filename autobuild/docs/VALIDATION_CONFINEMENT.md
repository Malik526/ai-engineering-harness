# Normal Validation Confinement (0.5)

Permanent invariant: **deterministic validation that can authorize a checkpoint
must execute through a controller-owned, fail-closed path.** Agent claims and
implementer-reported tests are never validation truth.

## Contract

`validation.commands` extends the existing validation framework. `name` is the
stable validation id; `kind` is setup, test, lint, typecheck, build, or other.
Use `command: [argv...]`. Legacy `run: "shell string"` remains supported through
`/bin/sh -c` but is marked `legacy-shell` in evidence. Exactly one is required.

Each command may set repository-relative `cwd`, integer `timeout_seconds`,
`required`, changed-file `paths`, explicit string `env`, and `network` (`none`
default, `host` opt-in). Reserved PATH/HOME/TMP/XDG/proxy/loader/controller keys
are rejected. Config may name ignored `validation.runtime_paths`; preflight
requires real non-symlink paths inside the project and mounts them read-only.

## Source And Filesystem

The controller's temporary Git index already creates one exact tree containing
tracked and eligible untracked implementation files. `git archive` materializes
that tree under a fresh controller temporary root. Normal validation sees:

- a writable copy of that exact source tree;
- private writable HOME, TMPDIR, XDG cache/config/state and build scratch;
- the active Python runtime and required system executables/libraries;
- the read-only controller worker/request and explicit runtime paths.

It does not see the actual source worktree, `.git`, user home, SSH credentials,
unrelated repositories, arbitrary parent/host paths, or host runtime sockets.
The minimal root itself is remounted read-only once its mountpoints exist, so a
write anywhere except the snapshot copy, a private `/tmp` tmpfs and the listed
scratch paths fails rather than landing in an ephemeral layer.
Commands in one attempt share the copy so setup/build outputs can feed later
commands and browser gates. The controller discards it after the attempt.

## Environment And Network

The sandbox starts with `--clearenv`. Autobuild supplies a deterministic PATH,
C locale, private HOME/TMP/XDG paths, CI marker, scratch path, and explicitly
configured variables. Evidence contains keys and a policy hash, never values.
Controller cloud/provider/Git/SSH secrets are not inherited. Explicit `env`
values are literal, non-secret settings: they live in the frozen run config, and
a command that prints its environment writes them to its raw log. 0.5 has no
secret-injection mechanism; validation that needs a real credential is out of scope.

`network: none` creates a new network namespace. `network: host` deliberately
keeps host networking and mounts only resolver files needed by tools; evidence
shows the opt-in. There is no ambient/automatic networking or domain allowlist.

## Outcomes And Lifecycle

Exit 0 is PASS; nonzero is FAIL. Missing tools/Bubblewrap, unsupported platform,
namespace/mount/worker/policy errors, unsafe cwd/logs, and timeout are ERROR.
Path-filtered commands are SKIPPED. There is no unsandboxed fallback: the
validation runner refuses to start without a controller source snapshot. Host
execution exists only for the manual completion check, which must request it
explicitly (`manual_host=True`), records `producer: manual`, and can never
authorize a checkpoint. A single output file is capped at 64 MiB. All commands
run so reviewers receive complete evidence. Required FAIL or ERROR makes the
aggregate non-PASS. A reviewer may request a fix with REVISE, but PASS cannot
override it and no checkpoint can occur.

The worker owns the command process group and TERM/KILL escalation. Bubblewrap's
PID namespace and `--die-with-parent` contain detached descendants. The outer
controller also owns and terminates the sandbox group on success, failure,
timeout, exception, and interruption.

## Evidence And Revision

Schema v2 evidence records run/attempt/upcoming review cycle, worktree/HEAD/exact
snapshot, brief and validation-policy hashes, id/argv/contract/cwd, required,
sandbox/network/environment policy, timing/duration, exit/status/detail, bounded
summaries, raw paths, and SHA-256/size for every raw log. `validation_history`
anchors each numbered manifest by hash. Integrity checks compare it with frozen
config, per-attempt Git evidence and controller state before review, revision,
resume and checkpoint. `autobuild evidence RUN [--attempt N]` verifies normal and
browser manifests.

Revision preserves old evidence as history, captures a new source tree, reruns
normal validation, reruns browser gates against the same disposable workspace,
and starts a fresh reviewer. Prior PASS never proves changed source.

## Limits

0.5 is Linux/Bubblewrap-only. It trusts the host kernel, configured validation
commands, active runtime binaries and explicitly mounted dependencies. It does
not add seccomp, cgroups/CPU/memory quotas, content scanning, deterministic
dependency hashes, distributed workers, CI integration, or cross-platform
sandbox backends. Explicit `network: host` grants ordinary host networking.
