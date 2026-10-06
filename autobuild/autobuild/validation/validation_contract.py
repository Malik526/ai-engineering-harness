"""Semantic config and immutable-evidence checks for confined normal validation."""

import hashlib
import json
import re
from pathlib import Path

from autobuild.validation.browser_contract import digest, safe_file


_RESERVED_ENV = {
    "PATH", "HOME", "TMPDIR", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "BASH_ENV", "ENV",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "AUTOBUILD_VALIDATION_SCRATCH",
}


def validation_config_errors(validation: dict) -> list[str]:
    errors = []
    names = [command["name"] for command in validation.get("commands", [])]
    if len(names) != len(set(names)):
        errors.append("validation.commands: duplicate command names")
    for command in validation.get("commands", []):
        for name, value in command.get("env", {}).items():
            if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name.startswith(("AUTOBUILD_", "LD_", "DYLD_"))
                    or name in _RESERVED_ENV):
                errors.append(f"validation command {command['name']}: environment key {name} is controller-owned or unsafe")
            if "\x00" in value:
                errors.append(f"validation command {command['name']}: environment values cannot contain NUL")
    return errors


def config_digest(config: dict) -> str:
    policy = {"version": config.get("version"), "validation": config.get("validation", {})}
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def evidence_errors(run_dir: Path, artifact: str, expected_hash: str) -> list[str]:
    path = run_dir / artifact
    try:
        if not safe_file(path, run_dir) or digest(path) != expected_hash:
            return ["validation evidence missing, moved or modified"]
        document = json.loads(path.read_text())
        from autobuild.common.schemas import schema_errors
        errors = schema_errors("validation", document)
        if errors:
            return errors
        required_passed = all(c["status"] in ("PASS", "SKIPPED") for c in document["commands"] if c["required"])
        if document["passed"] != required_passed:
            errors.append("validation aggregate does not match required command statuses")
        names = [command["name"] for command in document["commands"]]
        if len(names) != len(set(names)):
            errors.append("validation evidence contains duplicate command ids")
        manifest_paths = [record["path"] for record in document["files"]]
        expected_logs = [command[key] for command in document["commands"]
                         for key in ("stdout_path", "stderr_path") if command[key]]
        if len(manifest_paths) != len(set(manifest_paths)) or sorted(manifest_paths) != sorted(expected_logs):
            errors.append("validation log manifest does not match command evidence")
        for command in document["commands"]:
            if (command["status"] == "PASS" and command["exit_code"] != 0) or (
                    command["status"] == "FAIL" and command["exit_code"] in (0, None)):
                errors.append("validation status does not match exit behavior")
        for record in document["files"]:
            target = run_dir / record["path"]
            if (not safe_file(target, run_dir) or target.stat().st_size != record["size_bytes"]
                    or digest(target) != record["sha256"]):
                errors.append("validation artifact missing, moved or modified: " + record["path"])
        return errors
    except (OSError, ValueError, KeyError, TypeError):
        return ["validation evidence is unreadable or malformed"]


def history_errors(run_dir: Path, state: dict) -> list[str]:
    errors, attempts = [], set()
    config_sha = None
    config_path = run_dir / "config.json"
    if config_path.exists():
        try:
            if not safe_file(config_path, run_dir):
                errors.append("frozen validation configuration is unsafe")
            else:
                config_sha = config_digest(json.loads(config_path.read_text()))
        except (OSError, ValueError, TypeError):
            errors.append("frozen validation configuration is unreadable")
    revisions = {record["attempt"]: record for record in state.get("revision_history", [])}
    for record in state.get("validation_history", []):
        expected = f"validation/cycle-{record['attempt']:02d}/results.json"
        if record["artifact"] != expected or record["attempt"] in attempts:
            errors.append("validation history attempt/path is inconsistent")
        attempts.add(record["attempt"])
        problems = evidence_errors(run_dir, record["artifact"], record["sha256"])
        errors.extend(problems)
        if not problems:
            document = json.loads((run_dir / record["artifact"]).read_text())
            if any(document[key] != state[key] for key in ("run_id", "worktree", "brief_sha256")) or any(
                    document[key] != record[key] for key in ("attempt", "review_cycle", "snapshot_tree", "passed")):
                errors.append("validation evidence identity does not match controller history")
            if config_sha is not None and document["config_sha256"] != config_sha:
                errors.append("validation evidence does not match frozen execution configuration")
            if revisions and record["attempt"] not in revisions:
                errors.append("validation evidence has no matching implementation attempt")
            git_path = run_dir / f"implementation/cycle-{record['attempt']:02d}/git.json"
            if revisions and not safe_file(git_path, run_dir):
                errors.append("implementation snapshot evidence is missing or unsafe")
            elif git_path.exists():
                try:
                    git_document = json.loads(git_path.read_text())
                    if (document["snapshot_tree"] != git_document["snapshot_tree"]
                            or document["head_commit"] != git_document["head_commit"]):
                        errors.append("validation evidence does not match its implementation snapshot")
                except (OSError, ValueError, KeyError, TypeError):
                    errors.append("implementation snapshot evidence is unreadable")
    return errors
