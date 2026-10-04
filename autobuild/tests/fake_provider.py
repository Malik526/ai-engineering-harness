"""Fake provider adapter and registry used by runner tests (no live agent calls)."""

import json
import sys
from pathlib import Path
from typing import Optional

from autobuild.agent_provider import AgentRequest
from autobuild.structured_output import validate_report
from autobuild.subprocess_adapter import SubprocessAdapter

FAKE_AGENT = Path(__file__).with_name("fake_agent.py")


class FakeAdapter(SubprocessAdapter):
    def build_command(self, request: AgentRequest) -> list[str]:
        return [sys.executable, str(FAKE_AGENT)]

    def parse_output(self, request: AgentRequest, stdout_file: Path) -> tuple[Optional[str], Optional[dict], Optional[str]]:
        lines = stdout_file.read_text().strip().splitlines() if stdout_file.exists() else []
        if not lines:
            return None, None, "agent produced no final message"
        try:
            report = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            return None, None, f"final message is not JSON: {exc}"
        report, error = validate_report(report, request.report_schema)
        return f"fake-{self.provider_id}", report, error


def _entry(name: str, executable: str = sys.executable) -> dict:
    return {"display_name": name, "executable": executable,
            "roles": ["planner", "implementer", "reviewer"], "adapter": "fake_provider:FakeAdapter"}


TEST_REGISTRY = {
    "version": 1,
    "providers": {
        "fake-a": _entry("Fake A"),
        "fake-b": _entry("Fake B"),
        "fake-missing": _entry("Fake Missing", executable="definitely-not-installed-autobuild"),
    },
}
