"""Provider-neutral classification of why an agent invocation failed.

Adapters recognise their own CLI's error text (autobuild/providers/adapters/) and report
one of these kinds; the controller decides from the kind alone. Only a closed
set of provider/session failures can ever justify rollover. Bad code, failing
tests, reviewer findings, timeouts and transient errors never do.
"""

import re
from dataclasses import dataclass
from typing import Iterable, Optional

# Provider-wide: the provider cannot serve any session right now. A replacement
# must be a different provider.
QUOTA_EXHAUSTED = "quota_exhausted"
PROVIDER_HARD_LIMIT = "provider_hard_limit"
PROVIDER_UNAVAILABLE = "provider_unavailable"  # non-retryable transport/authentication failure
# Session-scoped: this session cannot continue, the provider itself may still work.
SESSION_UNAVAILABLE = "session_unavailable"  # the recorded session cannot be resumed
SESSION_EXHAUSTED = "session_exhausted"  # the session hit a hard limit such as its context window
# Never rollover triggers.
TRANSIENT = "transient"
SCHEMA_REJECTED = "schema_rejected"  # adapter/contract defect: a replacement would hide it
TIMEOUT = "timeout"
INTERRUPTED = "interrupted"
INVALID_OUTPUT = "invalid_output"
UNKNOWN = "unknown"

PROVIDER_SCOPED = frozenset({QUOTA_EXHAUSTED, PROVIDER_HARD_LIMIT, PROVIDER_UNAVAILABLE})
SESSION_SCOPED = frozenset({SESSION_UNAVAILABLE, SESSION_EXHAUSTED})
ROLLOVER_ELIGIBLE = PROVIDER_SCOPED | SESSION_SCOPED
ALL_KINDS = ROLLOVER_ELIGIBLE | {TRANSIENT, SCHEMA_REJECTED, TIMEOUT, INTERRUPTED, INVALID_OUTPUT, UNKNOWN}

_MAX_DETAIL = 500


@dataclass(frozen=True)
class ProviderFailure:
    kind: str
    detail: str

    @property
    def rollover_eligible(self) -> bool:
        return self.kind in ROLLOVER_ELIGIBLE

    def as_record(self) -> dict[str, str]:
        return {"kind": self.kind, "detail": self.detail}


def match_failure(text: str, patterns: Iterable[tuple[str, str]]) -> Optional[ProviderFailure]:
    """First (kind, regex) pattern found in the provider's own error text, in table order."""
    for kind, pattern in patterns:
        found = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if found:
            start = text.rfind("\n", 0, found.start()) + 1
            end = text.find("\n", found.end())
            line = text[start:end if end != -1 else len(text)].strip()
            return ProviderFailure(kind, line[:_MAX_DETAIL])
    return None
