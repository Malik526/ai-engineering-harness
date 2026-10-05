"""Semantic browser-config checks and integrity checks for controller evidence."""

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from autobuild.command_guard import is_within


def browser_config_errors(gates: list[dict]) -> list[str]:
    errors = []
    ids = [gate["id"] for gate in gates]
    if len(set(ids)) != len(ids):
        errors.append("validation.browser_gates: duplicate gate IDs")
    for gate in gates:
        if gate["id"] == "missing-browser-coverage":
            errors.append("browser gate ID missing-browser-coverage is controller-reserved")
        for name in gate.get("env", {}):
            if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name.startswith(("AUTOBUILD_", "LD_", "DYLD_"))
                    or name in {"PATH", "HOME", "TMPDIR", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "BASH_ENV", "ENV",
                                "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
                                "PLAYWRIGHT_BROWSERS_PATH", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"}):
                errors.append(f"browser gate {gate['id']}: environment key {name} is controller-owned or unsafe")
        if any("\x00" in value for value in gate.get("env", {}).values()):
            errors.append(f"browser gate {gate['id']}: environment values cannot contain NUL")
        for pattern in gate.get("artifacts", []):
            if "\\" in pattern or pattern.startswith("~") or ".git" in Path(pattern).parts:
                errors.append(f"browser gate {gate['id']}: unsafe artifact pattern")
        if gate.get("service"):
            try:
                url = urlsplit(gate["service"]["ready_url"])
                valid = (url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost", "::1")
                         and url.port is not None and not url.username and not url.password and not url.fragment)
            except ValueError:
                valid = False
            if not valid:
                errors.append(f"browser gate {gate['id']}: ready_url must be explicit loopback HTTP with a port")
    return errors


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            hasher.update(block)
    return hasher.hexdigest()


def evidence_errors(run_dir: Path, artifact: str, expected_hash: str) -> list[str]:
    path = run_dir / artifact
    try:
        if not safe_file(path, run_dir) or digest(path) != expected_hash:
            return ["browser evidence missing, moved or modified"]
        document = json.loads(path.read_text())
        from autobuild.schemas import schema_errors
        errors = schema_errors("browser", document)
        if errors:
            return errors
        if document["passed"] != all(g["status"] == "PASS" for g in document["gates"] if g["required"]):
            errors.append("browser aggregate does not match required gate statuses")
        for gate in document["gates"]:
            if (gate["status"] == "PASS" and gate["exit_code"] != 0) or (gate["status"] == "FAIL" and gate["exit_code"] in (0, None)):
                errors.append("browser status does not match exit behavior")
        for record in document["files"]:
            target = run_dir / record["path"]
            if (not safe_file(target, run_dir)
                    or target.stat().st_size != record["size_bytes"] or digest(target) != record["sha256"]):
                errors.append("browser artifact missing, moved or modified: " + record["path"])
        return errors
    except (OSError, ValueError, KeyError, TypeError):
        return ["browser evidence is unreadable or malformed"]


def safe_file(path: Path, root: Path) -> bool:
    if not is_within(path, root) or not path.is_file() or path.stat().st_nlink != 1:
        return False
    return not any(parent.is_symlink() for parent in (path, *path.parents) if parent != root)


def history_errors(run_dir: Path, state: dict) -> list[str]:
    errors, attempts = [], set()
    for record in state.get("browser_history", []):
        expected = f"browser/cycle-{record['attempt']:02d}/results.json"
        if record["artifact"] != expected or record["attempt"] in attempts:
            errors.append("browser history attempt/path is inconsistent")
        attempts.add(record["attempt"])
        problems = evidence_errors(run_dir, record["artifact"], record["sha256"])
        errors.extend(problems)
        if not problems:
            document = json.loads((run_dir / record["artifact"]).read_text())
            if any(document[key] != state[key] for key in ("run_id", "worktree", "brief_sha256")) or any(
                    document[key] != record[key] for key in ("attempt", "review_cycle", "snapshot_tree", "passed")):
                errors.append("browser evidence identity does not match controller history")
    return errors
