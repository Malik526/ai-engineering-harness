"""Shared fail-closed Bubblewrap policy for every controller-owned validation process."""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
from typing import Mapping, Sequence

@dataclass(frozen=True)
class SandboxPolicy:
    label: str
    execution_root: Path
    writable_root: Path
    input_root: Path
    environment: Mapping[str, str]
    network: str = "none"
    read_only_paths: tuple[Path, ...] = ()
    read_only_bindings: tuple[tuple[Path, Path], ...] = ()
    writable_paths: tuple[Path, ...] = ()
    host_root_readonly: bool = False


def isolated_environment(writable: Path, explicit: Mapping[str, str], *, browser: bool = False) -> dict[str, str]:
    paths = [str(Path(sys.prefix) / "bin"), "/usr/local/bin", "/usr/bin", "/bin"]
    for name in ("node", "npm"):
        binary = shutil.which(name)
        if binary:
            parent = str(Path(binary).parent.resolve())
            if parent not in paths:
                paths.insert(0, parent)
    environment = {
        "PATH": os.pathsep.join(paths), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "HOME": str(writable / "home"), "TMPDIR": "/tmp", "XDG_CACHE_HOME": str(writable / "cache"),
        "XDG_CONFIG_HOME": str(writable / "config"), "XDG_STATE_HOME": str(writable / "state"), "CI": "1",
        **explicit,
    }
    if browser:
        environment.update(PLAYWRIGHT_BROWSERS_PATH=str(Path.home() / ".cache/ms-playwright"),
                           AUTOBUILD_BROWSER_OUTPUT=str(writable / "outputs"))
    else:
        environment["AUTOBUILD_VALIDATION_SCRATCH"] = str(writable / "scratch")
    return environment


def sandbox_command(policy: SandboxPolicy, argv: Sequence[str]) -> list[str]:
    if sys.platform != "linux":
        raise RuntimeError(f"{policy.label} requires the Linux Bubblewrap backend")
    executable = shutil.which("bwrap")
    if not executable:
        raise RuntimeError(f"{policy.label} requires bubblewrap with user/PID namespaces")
    if policy.network not in ("none", "host"):
        raise ValueError("sandbox network policy must be none or host")

    command = [executable, "--die-with-parent", "--new-session", "--unshare-user", "--unshare-pid",
               "--unshare-ipc", "--unshare-uts", "--cap-drop", "ALL"]
    if policy.network == "none":
        command.append("--unshare-net")
    if policy.host_root_readonly:
        command += ["--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev",
                    "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/home", "--tmpfs", "/root"]
    else:
        command += ["--tmpfs", "/", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/run",
                    "--dir", "/home", "--dir", "/root", "--dir", "/etc", "--ro-bind", "/usr", "/usr"]
        for link, target in (("/bin", "usr/bin"), ("/lib", "usr/lib"), ("/lib64", "usr/lib64")):
            command += ["--symlink", target, link]
        for path in (Path("/etc/ld.so.cache"), Path("/etc/ssl"), Path("/etc/localtime")):
            if path.exists():
                command += ["--ro-bind", str(path), str(path)]
        if policy.network == "host":
            for path in (Path("/etc/hosts"), Path("/etc/nsswitch.conf"), Path("/etc/resolv.conf")):
                if path.exists():
                    command += ["--ro-bind", str(path.resolve()), str(path)]

    assets = {Path(sys.prefix).resolve(), policy.input_root.resolve()}
    for name in ("node", "npm"):
        binary = shutil.which(name)
        if binary and Path(binary).resolve().is_relative_to(Path.home()):
            assets.add(Path(binary).resolve().parent.parent)
    assets.update(path.resolve() for path in policy.read_only_paths)
    for path in sorted(assets, key=lambda value: (len(value.parts), str(value))):
        command += ["--ro-bind", str(path), str(path)]
    for source, destination in policy.read_only_bindings:
        command += ["--ro-bind", str(source.resolve()), str(destination.resolve())]
    writable = {policy.writable_root.resolve(), *(path.resolve() for path in policy.writable_paths)}
    for path in sorted(writable, key=lambda value: (len(value.parts), str(value))):
        command += ["--bind", str(path), str(path)]
    if not policy.host_root_readonly:
        # Seal the minimal root after every mountpoint exists: only the private /tmp
        # tmpfs and the explicit writable binds above accept writes.
        command += ["--remount-ro", "/"]
    command.append("--clearenv")
    for key, value in sorted(policy.environment.items()):
        command += ["--setenv", key, value]
    return command + ["--chdir", str(policy.execution_root), "--", *argv]
