"""Browser policy adapter for the shared fail-closed Bubblewrap layer."""

from pathlib import Path
import sys

from autobuild.paths import CORE_ROOT
from autobuild.sandbox import SandboxPolicy, isolated_environment as shared_environment, sandbox_command as shared_command


def sandbox_command(worktree: Path, inputs: Path, writable: Path, environment: dict) -> list[str]:
    assets = []
    browsers = Path.home() / ".cache/ms-playwright"
    if browsers.is_dir():
        assets.append(browsers)
    assets.append(CORE_ROOT)
    policy = SandboxPolicy(label="browser gates", execution_root=worktree, writable_root=writable,
                           input_root=inputs, environment=environment, network="none",
                           read_only_paths=tuple(assets + [worktree]), host_root_readonly=True)
    return shared_command(policy, [sys.executable, "-I", str(CORE_ROOT / "autobuild/browser_worker.py"),
                                   str(inputs / "request.json")])


def isolated_environment(writable: Path, explicit: dict) -> dict[str, str]:
    return shared_environment(writable, explicit, browser=True)
