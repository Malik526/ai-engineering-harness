"""Collect only fresh sandbox outputs; reject links, special files and secret names."""

import os
from pathlib import Path
import shutil
import stat

from autobuild.browser_contract import digest
from autobuild.secret_files import secret_like


def file_record(path: Path, run_dir: Path) -> dict:
    return {"path": path.relative_to(run_dir).as_posix(), "size_bytes": path.stat().st_size,
            "sha256": digest(path)}


def collect(source: Path, destination: Path, patterns: list[str], run_dir: Path) -> list[dict]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError("artifact output root is not a real directory")
    selected = set()
    # Inspect the complete output tree before globbing: glob must never follow links.
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("artifact output contains a link or special file")
            if ".git" in path.relative_to(source).parts or (path.is_file() and (path.stat().st_nlink != 1 or secret_like([path.name]))):
                raise ValueError("artifact output contains a hard link or secret-like filename")
    for pattern in patterns:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts or "\\" in pattern:
            raise ValueError("unsafe artifact pattern")
        matches = {path for path in source.glob(pattern) if path.is_file()}
        if not matches:
            raise ValueError("declared artifact pattern has no files: " + pattern)
        selected.update(matches)
    if len(selected) > 200 or sum(path.stat().st_size for path in selected) > 64 * 1024 * 1024:
        raise ValueError("artifact collection exceeds 200 files or 64 MiB")
    records = []
    for path in sorted(selected):
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream, target.open("xb") as output:
            shutil.copyfileobj(stream, output)
        records.append(file_record(target, run_dir))
    return records
