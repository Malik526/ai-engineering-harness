# Controller-Owned Browser Gates

Agents may consume browser evidence, but the Autobuild controller owns execution
and truth of deterministic browser gates. Browser test frameworks stay in the
project; Autobuild orchestrates them, not browser agents or AI-inferred validation.

## Configuration

Extend `.autobuild/config.yaml` explicitly:

```yaml
validation:
  browser_tool: playwright
  require_clean_git_before_start: true
  commands:
    - {name: tests, kind: test, run: npm test}
  browser_gates:
    - id: web-smoke
      kind: e2e
      command: [node, smoke.cjs]
      cwd: web
      required: true
      enabled: true
      timeout_seconds: 180
      env: {PUBLIC_FIXTURE_MODE: smoke}
      artifacts: [screenshot.png, trace.zip, report/**]
      service:
        command: [npm, run, dev, --, --host, 127.0.0.1, --port, '3000']
        ready_url: http://127.0.0.1:3000
        timeout_seconds: 60
```

IDs are unique lowercase tokens, kind is browser/e2e, command is a nonempty argv
array (no implicit shell). Cwd is worktree-relative and cannot resolve outside
it; service cwd defaults to gate cwd. Gate timeout defaults to 180 seconds;
required/enabled default true. Maximum 20 gates, sequential execution. No changed-
path inference or automatic gate selection. `browser_tool` remains descriptive;
only `browser_gates` controls execution. `missing-browser-coverage` is reserved.

Every artifact pattern must match at least one regular output file, even on FAIL.
Use a finally/teardown hook to preserve failure screenshots/traces/reports.
All paths are relative to `AUTOBUILD_BROWSER_OUTPUT`, a new writable output
directory provided by the controller. The worktree itself is read-only: install
dependencies/build outputs during confined normal validation first, then configure test
reporters/caches to use the output directory or private temporary storage.
Explicit env is for nonsecret test settings only. PATH/HOME/temp, preload/interpreter
hooks, proxies and controller-owned keys cannot be overridden. Environment values
are not dumped into browser summaries; keys and a full-environment hash are recorded.
The frozen config already contains explicit values, so never put credentials there.

## Results And Review

| Controller observation | Status |
| --- | --- |
| Test exits 0, lifecycle/artifact contract valid | PASS |
| Test exits nonzero, lifecycle/artifact contract valid | FAIL |
| Missing tool/sandbox, timeout, service failure, malformed or missing artifact | ERROR |
| Gate explicitly disabled, or brief-required coverage absent | SKIPPED |

Optional non-PASS gates remain visible but do not mechanically block checkpoint.
Required non-PASS gates always block, even if reviewer returns PASS. A brief with
`browser_required: true` needs at least one enabled required gate; otherwise a
synthetic required SKIPPED record describes missing coverage. With neither
configured gates nor a browser-required brief, 0.3 behavior remains unchanged.

Normal validation must pass first. Browser failures then reach a fresh reviewer
through the existing PASS/REVISE/BLOCK schema. Fixable FAIL should produce REVISE;
tool/coverage prerequisites should produce BLOCK. REVISE resumes the same
implementer, reruns both validation classes, and gives a fresh reviewer new evidence.
Review remains bounded by max_review_cycles. No automated error repair/fallback.

Numbered evidence lives under `browser/cycle-NN/` (NN is implementation attempt;
the upcoming review cycle is recorded separately). All prior artifacts remain,
including failures. `autobuild evidence RUN --attempt NN` verifies hashes and
prints gate outcomes, exit codes, manifest locations and artifact counts.
There is no standalone gate runner that bypasses snapshot or review controls.

## Service And Process Lifecycle

The controller owns start -> readiness -> test -> cleanup in one private network
namespace. Readiness requires explicit loopback HTTP with a port and a 2xx
response; proxy use and redirects are disabled. The declared service must remain
alive. Host servers cannot be reused or accidentally satisfy readiness. Remote
URLs, external browser services and authenticated production endpoints are not
supported. A service sharing a namespace with its trusted test may launch its
own children; process groups are terminated and namespace exit kills descendants.

Readiness and test have separate deadlines. A parent watchdog adds a cleanup
allowance. Cleanup runs on PASS, FAIL, ERROR, exceptions and Ctrl-C using TERM,
bounded wait, then KILL. Worker raw logs have a 64 MiB per-file limit; summaries
are at most 2,048 characters. Artifact collection permits at most 200 files and
64 MiB total per gate. Timeout/invalid output cannot become PASS from tool JSON.

## Platform And Safety

Linux with `bwrap` and usable user/network/PID namespaces is required. No native
macOS/Windows backend or unsandboxed fallback exists. In managed restricted
execution environments, sandbox creation may be denied: the gate records ERROR
and cannot checkpoint. Have the human enable the prerequisite; never weaken it.
Browser binaries and runtime dependencies must already be installed. Standard
system tools, the active Python runtime, home-installed Node runtime and the
user's Playwright browser cache are exposed read-only alongside the worktree.

Fresh output roots, no-follow collection, link/special-file/secret-name checks
and hash manifests prevent arbitrary host-path artifact collection. Worktree
and Git metadata are not writable. Host home, temp and runtime socket paths are
hidden; external network is absent. This is scoped browser confinement, not a
full hostile-process security boundary. System/controller assets are readable;
normal validation uses 0.5's shared snapshot sandbox; content scanning/resource quotas are
not implemented, and sensitive data already inside the worktree is not sanitized.
Git snapshot identity excludes ignored build outputs and dependency trees;
installed runtime/browser binary hashes are not captured in 0.4. Pin dependencies
and browser versions in the project to improve replay reproducibility.

Existing tooling references: [Playwright server orchestration](https://playwright.dev/docs/test-webserver)
and [Bubblewrap design](https://github.com/containers/bubblewrap/blob/main/README.md).
Autobuild uses its own explicit service lifecycle rather than relying on a
framework's reuseExistingServer policy, so readiness always targets this run.
