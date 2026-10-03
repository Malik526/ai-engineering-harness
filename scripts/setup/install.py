#!/usr/bin/env python3
"""Link canonical harness assets into the runtime locations agents read.

Reads scripts/setup/links.manifest and, for each <source> <target> pair,
reports or establishes `target -> <repo>/<source>` as an absolute symlink.

    install.py            check only (default); exit 1 unless every link is OK
    install.py --apply    create missing links
    install.py --adopt    also replace targets whose content is identical to the
                          source, after moving the original into a backup dir

It never overwrites a target that differs from the source; that is reported as
CONFLICT for a human to resolve. Standard library only, so it runs before any
virtualenv exists.
"""

import argparse
import filecmp
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "scripts" / "setup" / "links.manifest"
BACKUP_ROOT = Path.home() / ".agents" / ".harness-backup"


def read_manifest() -> list[tuple[Path, Path]]:
    """Return (absolute source, absolute target) pairs from the manifest."""
    pairs = []
    for number, raw in enumerate(MANIFEST.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise SystemExit(f"{MANIFEST}:{number}: expected '<source> <target>', got {raw!r}")
        pairs.append((REPO_ROOT / parts[0], Path(os.path.expanduser(parts[1]))))
    return pairs


def same_content(a: Path, b: Path) -> bool:
    """Byte-identical files, or directory trees with identical files and names."""
    if a.is_file() and b.is_file():
        return filecmp.cmp(a, b, shallow=False)
    if a.is_dir() and b.is_dir():
        cmp = filecmp.dircmp(a, b)
        if cmp.left_only or cmp.right_only or cmp.funny_files:
            return False
        _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
        return not mismatch and not errors and all(same_content(a / d, b / d) for d in cmp.common_dirs)
    return False


def status(source: Path, target: Path) -> str:
    """OK | MISSING | ADOPTABLE | CONFLICT | NO_SOURCE for one manifest entry."""
    if not source.exists():
        return "NO_SOURCE"
    if target.is_symlink():
        return "OK" if target.resolve() == source.resolve() else "CONFLICT"
    if not target.exists():
        return "MISSING"
    return "ADOPTABLE" if same_content(source, target) else "CONFLICT"


def backup(target: Path, stamp: str) -> Path:
    """Move `target` under BACKUP_ROOT/<stamp>/, keeping its path relative to $HOME."""
    destination = BACKUP_ROOT / stamp / target.relative_to(Path.home())
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(destination))
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="create missing links")
    parser.add_argument("--adopt", action="store_true", help="also replace identical copies (implies --apply)")
    args = parser.parse_args()
    apply = args.apply or args.adopt
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    problems = 0

    for source, target in read_manifest():
        state = status(source, target)
        note = ""
        if apply and state == "MISSING":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source)
            state, note = "LINKED", ""
        elif args.adopt and state == "ADOPTABLE":
            saved = backup(target, stamp)
            target.symlink_to(source)
            state, note = "ADOPTED", f"original saved to {saved}"
        elif state == "CONFLICT":
            current = os.readlink(target) if target.is_symlink() else "existing content differs"
            note = f"({current}) — resolve by hand"
        if state not in ("OK", "LINKED", "ADOPTED"):
            problems += 1
        print(f"{state:<9} {target} -> {source.relative_to(REPO_ROOT)} {note}".rstrip())

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
