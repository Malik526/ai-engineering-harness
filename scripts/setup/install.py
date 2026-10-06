#!/usr/bin/env python3
"""Link canonical harness assets into the runtime locations agents read.

Reads scripts/setup/links.manifest and, for each <source> <target> pair,
reports or establishes `target -> <repo>/<source>` as an absolute symlink.
Also reconciles the owned runtime fragments for installed provider executables,
and reports whether ~/.local/bin (where commands such as `autobuild` are linked)
is on PATH. It never edits shell startup files.

    install.py            check only (default); exit 1 unless every link is OK
    install.py --apply    create missing links and reconcile runtime fragments
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

from runtime_guards import installed_providers, reconcile, runtime_directory

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "scripts" / "setup" / "links.manifest"


def read_manifest(home: Path | None = None, providers: list[str] | None = None) -> list[tuple[Path, Path]]:
    """Return (absolute source, absolute target) pairs from the manifest."""
    pairs = []
    for number, raw in enumerate(MANIFEST.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise SystemExit(f"{MANIFEST}:{number}: expected '<source> <target>', got {raw!r}")
        target = (home or Path.home()) / parts[1].removeprefix("~/")
        runtime = next((name for name in ("claude", "codex") if parts[1].startswith(f"~/.{name}/")), None)
        if providers is not None and runtime and runtime not in providers:
            continue
        if runtime:
            target = runtime_directory(home or Path.home(), runtime) / parts[1].split("/", 2)[2]
        pairs.append((REPO_ROOT / parts[0], target))
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


def path_report(home: Path, pairs: list[tuple[Path, Path]]) -> str:
    """Whether the user-local command directory is on PATH. A warning, never a failure or an edit."""
    commands = home / ".local" / "bin"
    if not any(target.parent == commands for _, target in pairs):
        return ""
    entries = [Path(entry).expanduser() for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    if any(entry.resolve() == commands.resolve() for entry in entries):
        return f"OK        {commands} is on PATH (commands: autobuild)"
    return (f"WARNING   {commands} is not on PATH, so `autobuild` will not be found. Add this line to your shell "
            f"profile (e.g. ~/.bashrc), then open a new shell: export PATH=\"$HOME/.local/bin:$PATH\"")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="create missing links")
    parser.add_argument("--adopt", action="store_true", help="also replace identical copies (implies --apply)")
    parser.add_argument("--home", type=Path, default=Path.home(), help="target home (isolated setup testing)")
    parser.add_argument("--check", action="store_true", help="explicit read-only check (the default)")
    args = parser.parse_args()
    args.home = args.home.expanduser().resolve()
    if args.check and (args.apply or args.adopt):
        parser.error("--check cannot be combined with --apply or --adopt")
    backup_root = args.home / ".agents" / ".harness-backup"
    apply = args.apply or args.adopt
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    problems = 0

    providers = installed_providers()
    pairs = read_manifest(args.home, providers)
    for source, target in pairs:
        state = status(source, target)
        note = ""
        if apply and state == "MISSING":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source)
            state, note = "LINKED", ""
        elif args.adopt and state == "ADOPTABLE":
            relative = target.relative_to(args.home) if target.is_relative_to(args.home) else Path("external") / target.name
            saved = backup_root / stamp / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(saved))
            target.symlink_to(source)
            state, note = "ADOPTED", f"original saved to {saved}"
        elif state == "CONFLICT":
            current = os.readlink(target) if target.is_symlink() else "existing content differs"
            note = f"({current}) — resolve by hand"
        if state not in ("OK", "LINKED", "ADOPTED"):
            problems += 1
        print(f"{state:<9} {target} -> {source.relative_to(REPO_ROOT)} {note}".rstrip())

    print(path_report(args.home, pairs))

    for report in reconcile(REPO_ROOT, args.home, providers, apply=apply):
        print(report)
        if report.startswith(("MISSING", "CONFLICT", "STALE")):
            problems += 1

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
