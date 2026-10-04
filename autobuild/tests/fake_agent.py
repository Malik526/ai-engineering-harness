"""Stand-in agent process for runner tests. Behaviour comes from FAKE_AGENT_MODE.

Reads the prompt on stdin like a real provider, works in its cwd (the run
worktree), and prints its report as the last stdout line.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPORT = {
    "implementation_summary": "Added feature.txt.",
    "files_changed": ["feature.txt"],
    "tests_reported": [{"command": "check", "outcome": "passed", "details": "ok"}],
    "documentation_changed": [],
    "assumptions": ["none"],
    "known_issues": [],
}


def real_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([os.environ["AUTOBUILD_REAL_GIT"], *args], capture_output=True, text=True)


def main() -> int:
    mode = os.environ.get("FAKE_AGENT_MODE", "write")
    prompt = sys.stdin.read()
    if mode == "fail":
        Path("partial.txt").write_text("half-finished work\n")
        print("simulated provider crash", file=sys.stderr)
        return 3
    if mode not in ("noop", "sleep"):
        Path("feature.txt").write_text("hello from the fake agent\n")
    if mode == "sleep":
        time.sleep(120)
    if mode == "bad_report":
        print("I did it, trust me")
        return 0
    if mode == "git_push":
        # Through PATH: must hit the guard shim and be refused.
        done = subprocess.run(["git", "push", "origin", "HEAD"], capture_output=True, text=True)
        Path("push-result.txt").write_text(f"{done.returncode}\n{done.stderr}")
    if mode == "agent_commit":
        real_git("add", "-A")
        real_git("-c", "user.name=a", "-c", "user.email=a@b", "commit", "-q", "-m", "sneaky")
    if mode == "move_main":
        head = real_git("rev-parse", "HEAD").stdout.strip()
        real_git("-c", "user.name=a", "-c", "user.email=a@b", "commit", "--allow-empty", "-q", "-m", "x")
        real_git("update-ref", "refs/heads/main", "HEAD", head)
    if mode == "secret":
        Path(".env").write_text("API_KEY=not-a-real-key\n")
    report = dict(REPORT, implementation_summary=f"mode={mode}; prompt_chars={len(prompt)}")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
