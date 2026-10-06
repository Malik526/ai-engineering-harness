"""Fake provider adapter and registry used by runner tests (no live agent calls)."""

import json
import sys
from pathlib import Path
from typing import Optional

from autobuild.agent_provider import AgentRequest
from autobuild.provider_failures import QUOTA_EXHAUSTED, SCHEMA_REJECTED, SESSION_UNAVAILABLE, TRANSIENT
from autobuild.structured_output import validate_report
from autobuild.subprocess_adapter import SubprocessAdapter

FAKE_AGENT = Path(__file__).with_name("fake_agent.py")


class FakeAdapter(SubprocessAdapter):
    def build_command(self, request: AgentRequest) -> list[str]:
        return [sys.executable, str(FAKE_AGENT), self.provider_id]

    reports_usage = True

    def parse_usage(self, request: AgentRequest) -> Optional[dict]:
        import os
        tokens = int(os.environ.get("FAKE_USAGE_TOKENS", "1000"))
        return {"input_tokens": tokens - tokens // 10, "output_tokens": tokens // 10, "total_tokens": tokens}

    def failure_patterns(self) -> list[tuple[str, str]]:
        return [(SCHEMA_REJECTED, r"input_schema"), (SESSION_UNAVAILABLE, r"No conversation found"),
                (QUOTA_EXHAUSTED, r"usage limit"),
                (TRANSIENT, r"overloaded")]

    def parse_output(self, request: AgentRequest, stdout_file: Path) -> tuple[Optional[str], Optional[dict], Optional[str]]:
        lines = stdout_file.read_text().strip().splitlines() if stdout_file.exists() else []
        if not lines:
            return None, None, "agent produced no final message"
        try:
            report = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            return None, None, f"final message is not JSON: {exc}"
        report, error = validate_report(report, request.report_schema)
        identity = request.resume_session_id or request.session_id
        if request.role == "reviewer":
            import os
            identity = os.environ.get("FAKE_REVIEW_SESSION", identity)
        return identity, report, error


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
