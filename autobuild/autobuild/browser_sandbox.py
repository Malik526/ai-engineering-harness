"""Fail-closed Linux browser sandbox. No host-network or unsandboxed fallback."""

import os
from pathlib import Path
import shutil
import sys

from autobuild.paths import CORE_ROOT


def sandbox_command(worktree: Path, inputs: Path, writable: Path, environment: dict) -> list[str]:
    if sys.platform != "linux":
        raise RuntimeError("browser gates require the Linux Bubblewrap backend")
    executable = shutil.which("bwrap")
    if not executable:
        raise RuntimeError("browser gates require bubblewrap with user/network/PID namespaces")
    command = [executable, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid",
               "--unshare-net", "--cap-drop", "ALL", "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev",
               "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/home", "--tmpfs", "/root"]
    # Expose only controller/runtime assets, never the user's credential-bearing home.
    assets = {CORE_ROOT.resolve(), Path(sys.prefix).resolve(), worktree.resolve(), inputs.resolve()}
    for name in ("node", "npm"):
        binary = shutil.which(name)
        if binary and Path(binary).resolve().is_relative_to(Path.home()):
            assets.add(Path(binary).resolve().parent.parent)
    browsers = Path.home() / ".cache/ms-playwright"
    if browsers.is_dir():
        assets.add(browsers.resolve())
    for path in sorted(assets, key=lambda value: len(value.parts)):
        command += ["--ro-bind", str(path), str(path)]
    command += ["--bind", str(writable), str(writable), "--clearenv"]
    for key, value in sorted(environment.items()):
        command += ["--setenv", key, value]
    return command + ["--chdir", str(worktree), "--", sys.executable, "-I", str(CORE_ROOT / "autobuild/browser_worker.py"),
                      str(inputs / "request.json")]


def isolated_environment(writable: Path, explicit: dict) -> dict[str, str]:
    paths = ["/usr/local/bin", "/usr/bin", "/bin"]
    node = shutil.which("node")
    if node:
        paths.insert(0, str(Path(node).resolve().parent))
    return {"PATH": os.pathsep.join(paths), "LANG": "C.UTF-8", "HOME": str(writable / "home"),
            "TMPDIR": "/tmp", "CI": "1",
            "PLAYWRIGHT_BROWSERS_PATH": str(Path.home() / ".cache/ms-playwright"),
            "AUTOBUILD_BROWSER_OUTPUT": str(writable / "outputs"), **explicit}
