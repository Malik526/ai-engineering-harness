"""Reconcile harness-owned runtime fragments without replacing user settings.

Shared by the installer and audit. No provider calls or authentication reads.
Only explicitly marked sections may be replaced; conflicts stop that provider.
"""

import ast
import copy
import fnmatch
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path

PROVIDERS = ("claude", "codex")
HOOK_MARKER = "# AI Engineering Harness: commit guard"
TEXT_MARKERS = ("<!-- BEGIN AI Engineering Harness -->", "<!-- END AI Engineering Harness -->")
RULE_MARKERS = ("# BEGIN AI Engineering Harness", "# END AI Engineering Harness")


def installed_providers() -> list[str]:
    return [name for name in PROVIDERS if shutil.which(name)]


def runtime_directory(home: Path, provider: str) -> Path:
    """Honor provider config roots only for the real home, not fake-home tests."""
    key = "CLAUDE_CONFIG_DIR" if provider == "claude" else "CODEX_HOME"
    configured = os.environ.get(key) if home == Path.home() else None
    return Path(configured).expanduser().resolve() if configured else home / f".{provider}"


def managed_text(current: str, canonical: str, markers: tuple[str, str]) -> tuple[str, str]:
    """Return status and desired text, preserving everything outside one block."""
    begin, end = markers
    lines = current.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == begin]
    ends = [i for i, line in enumerate(lines) if line.strip() == end]
    if not starts and not ends:
        return "MISSING", current + ("\n" if current and not current.endswith("\n") else "") + canonical
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("ambiguous or incomplete harness ownership markers")
    start, finish = starts[0], ends[0] + 1
    block = "".join(lines[start:finish])
    desired = "".join(lines[:start]) + canonical + "".join(lines[finish:])
    return ("PASS" if block == canonical else "STALE"), desired


def _permission_matches(rule: str, command: str) -> bool:
    if rule in ("Bash", "Bash(*)"):
        return True
    if not rule.startswith("Bash(") or not rule.endswith(")"):
        return False
    pattern = rule[5:-1].replace(":*", " *")
    if re.match(r"(?:\S*/)?git\s+commit\b", pattern):
        return True
    try:
        tokens = shlex.split(pattern)
        if tokens and Path(tokens[0]).name == "git":
            index = 1
            while index < len(tokens) and tokens[index].startswith("-"):
                index += 2 if tokens[index] in ("-C", "-c", "--git-dir", "--work-tree", "--config-env", "--exec-path", "--namespace") else 1
            if index < len(tokens) and tokens[index] == "commit":
                return True
    except ValueError:
        pass
    return fnmatch.fnmatchcase(command, pattern) or fnmatch.fnmatchcase(command + " -m x", pattern)


def _claude_settings(current: dict, fragment: dict, repo: Path) -> tuple[list[str], dict]:
    desired = copy.deepcopy(current)
    problems = []
    permissions = desired.setdefault("permissions", {})
    hooks = desired.setdefault("hooks", {})
    if not isinstance(permissions, dict) or not isinstance(hooks, dict):
        raise ValueError("permissions and hooks must be objects")
    for name in ("allow", "ask", "deny"):
        values = permissions.get(name, [])
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"permissions.{name} must be a list of strings")
    probes = ("git commit", "git -C /repo commit", "git -c user.name=x commit", "/usr/bin/git commit")
    for name in ("allow", "deny"):
        if any(_permission_matches(rule, command) for rule in permissions.get(name, []) for command in probes):
            problems.append(f"CONFLICT claude: permissions.{name} overlaps commit approval; resolve user rules")
    if current.get("disableAllHooks") or current.get("allowManagedHooksOnly"):
        problems.append("CONFLICT claude: runtime disables user hooks")
    if permissions.get("defaultMode") in ("bypassPermissions", "dontAsk"):
        problems.append("CONFLICT claude: defaultMode prevents interactive commit approval")
    ask = permissions.setdefault("ask", [])
    if fragment["permissions"]["ask"][0] not in ask:
        problems.append("MISSING claude: required commit ask rule")
        ask.extend(fragment["permissions"]["ask"])

    entries = hooks.setdefault("PreToolUse", [])
    if not isinstance(entries, list):
        raise ValueError("hooks.PreToolUse must be a list")
    expected = fragment["hooks"]["PreToolUse"][0]
    managed = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks", []), list):
            raise ValueError("invalid PreToolUse hook group")
        for hook in entry.get("hooks", []):
            if not isinstance(hook, dict):
                raise ValueError("invalid hook handler")
            command = hook.get("command", "")
            if not isinstance(command, str):
                raise ValueError("hook command must be a string")
            if HOOK_MARKER in command:
                managed.append((entry, hook))
            elif "git_commit_guard.py" in command:
                # Recognize the previous unmarked canonical hook, but never adopt it.
                words = shlex.split(command)
                if len(words) >= 2 and Path(os.path.expanduser(words[1])).resolve() == (repo / "scripts/hooks/git_commit_guard.py").resolve():
                    continue
                problems.append("CONFLICT claude: unowned commit hook points outside the canonical harness")
    if len(managed) > 1:
        problems.append("CONFLICT claude: multiple harness-owned commit hooks")
    elif managed:
        entry, hook = managed[0]
        if entry.get("matcher") != "Bash" or hook != expected["hooks"][0] or "if" in entry:
            problems.append("STALE claude: harness commit hook differs from canonical fragment")
            entry["hooks"].remove(hook)
            # Never change a matcher shared by unrelated hooks.
            if not entry["hooks"]:
                entries.remove(entry)
            entries.append(copy.deepcopy(expected))
    else:
        problems.append("MISSING claude: harness-owned canonical commit hook")
        entries.append(copy.deepcopy(expected))
    if not (repo / "scripts/hooks/git_commit_guard.py").is_file():
        problems.append("CONFLICT claude: canonical commit hook script is missing")
    return problems, desired


def _codex_conflicts(text: str, canonical: str) -> list[str]:
    """Inspect literal prefix rules without executing user-controlled Starlark.

    Advanced Starlark is refused for reconciliation rather than interpreted.
    Codex applies forbidden > prompt > allow, so allows cannot override prompts.
    """
    def rules(source):
        parsed = ast.parse(source)
        result = []
        for statement in parsed.body:
            if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call)
                    and isinstance(statement.value.func, ast.Name) and statement.value.func.id == "prefix_rule"
                    and not statement.value.args):
                raise ValueError("rules audit supports only literal prefix_rule calls; inspect advanced Starlark manually")
            values = {item.arg: ast.literal_eval(item.value) for item in statement.value.keywords}
            if len(values) != len(statement.value.keywords) or set(values) - {"pattern", "decision", "justification", "match", "not_match"}:
                raise ValueError("unknown or duplicate prefix_rule fields")
            pattern, decision = values.get("pattern"), values.get("decision", "allow")
            if not isinstance(pattern, list) or not pattern or decision not in ("allow", "prompt", "forbidden"):
                raise ValueError("invalid prefix_rule pattern or decision")
            for item in pattern:
                if not isinstance(item, str) and not (isinstance(item, list) and item and all(isinstance(v, str) for v in item)):
                    raise ValueError("prefix_rule pattern must contain literal strings or unions")
            result.append((pattern, decision))
        return result

    prompts = [pattern for pattern, decision in rules(canonical) if decision == "prompt"]

    def commit_prefix(pattern):
        """A forbidden read after global options does not forbid a commit."""
        positions = [set(item if isinstance(item, list) else [item]) for item in pattern]
        pending = [1]
        while pending:
            index = pending.pop()
            if index >= len(positions):
                return True
            for word in positions[index]:
                if word == "commit":
                    return True
                if word.startswith("-"):
                    step = 2 if word in ("-C", "-c", "--git-dir", "--work-tree", "--config-env", "--exec-path", "--namespace") else 1
                    pending.append(index + step)
        return False

    for pattern, decision in rules(text):
        if decision != "forbidden":
            continue
        if commit_prefix(pattern) and any(all(set(a if isinstance(a, list) else [a]) & set(b if isinstance(b, list) else [b])
                                             for a, b in zip(prompt, pattern)) for prompt in prompts):
            return ["CONFLICT codex: forbidden rule overlaps required commit approval; resolve user rules"]
    return []


def _write(path: Path, content: str, expected: str | None) -> None:
    """Atomic replacement, preserving mode and refusing symlink targets."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.read_text() if path.exists() else None) != expected:
        raise OSError(f"{path}: configuration changed since preflight; rerun reconciliation")
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, name = tempfile.mkstemp(prefix=".harness-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def reconcile(repo: Path, home: Path, providers: list[str], *, apply: bool = False) -> list[str]:
    """Preflight every file per provider; write only if that provider has no conflict."""
    reports = []
    for provider in PROVIDERS:
        if provider not in providers:
            reports.append(f"SKIP {provider}: executable not installed")
            continue
        directory = runtime_directory(home, provider)
        adapter = directory / ("CLAUDE.md" if provider == "claude" else "AGENTS.md")
        guard = directory / ("settings.json" if provider == "claude" else "rules/default.rules")
        changes = []
        findings = []
        try:
            override = directory / "AGENTS.override.md"
            if provider == "codex" and override.exists() and override.read_text().strip():
                raise ValueError("AGENTS.override.md supersedes the managed adapter; reconcile it manually")
            for path in (adapter, guard):
                if path.is_symlink() or (path.exists() and not path.is_file()):
                    raise ValueError(f"{path}: refusing non-regular or symlink configuration")
            original_adapter = adapter.read_text() if adapter.exists() else None
            state, text = managed_text(original_adapter or "",
                                       (repo / f"runtime/{provider}/adapter.fragment.md").read_text(), TEXT_MARKERS)
            findings.append(f"{state} {provider}: adapter shared-policy section")
            if state != "PASS":
                changes.append((adapter, text, original_adapter, "adapter shared-policy section"))
            if provider == "claude":
                original_guard = guard.read_text() if guard.exists() else None
                current = json.loads(original_guard) if original_guard is not None else {}
                if not isinstance(current, dict):
                    raise ValueError("settings root must be an object")
                fragment = json.loads((repo / "runtime/claude/settings.fragment.json").read_text())
                command = fragment["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
                fragment["hooks"]["PreToolUse"][0]["hooks"][0]["command"] = command.replace(
                    "{commit_hook}", shlex.quote(str(repo / "scripts/hooks/git_commit_guard.py")))
                issues, desired = _claude_settings(current, fragment, repo)
                findings.extend(issues or ["PASS claude: commit ask rule and canonical hook"])
                if desired != current:
                    changes.append((guard, json.dumps(desired, indent=2) + "\n", original_guard, "commit ask rule / canonical hook"))
            else:
                canonical = (repo / "runtime/codex/default.rules").read_text()
                original_guard = guard.read_text() if guard.exists() else None
                current = original_guard or ""
                state, desired = managed_text(current, canonical, RULE_MARKERS)
                findings.append(f"{state} codex: canonical commit prompt rules")
                # Also inspect other loaded user rule files; don't print their contents.
                for path in sorted(guard.parent.glob("*.rules")):
                    if path != guard:
                        findings.extend(_codex_conflicts(path.read_text(), canonical))
                findings.extend(_codex_conflicts(desired, canonical))
                if state != "PASS":
                    changes.append((guard, desired, original_guard, "canonical commit prompt rules"))
        except (OSError, ValueError, SyntaxError, TypeError) as exc:
            findings.append(f"CONFLICT {provider}: {exc}")
        if apply and not any(row.startswith("CONFLICT") for row in findings):
            try:
                for path, content, expected, label in changes:
                    _write(path, content, expected)
                    reports.append(f"UPDATED {provider}: {path} ({label})")
                reports.extend(row for row in findings if row.startswith("PASS"))
            except OSError as exc:
                reports.append(f"CONFLICT {provider}: cannot write configuration: {exc}")
        else:
            reports.extend(findings)
    return reports
