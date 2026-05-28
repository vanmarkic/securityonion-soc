"""Request context — carries auth identity through the request lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

SYSTEM_ID = "00000000-0000-0000-0000-000000000000"
AGENT_ID = "00000000-0000-0000-0000-000000000001"


@dataclass(frozen=True)
class RequestContext:
    """Immutable request context holding the authenticated user's identity."""

    requestor_id: str
    username: str

    @classmethod
    def system(cls) -> RequestContext:
        """Create a context for system-initiated operations."""
        return cls(requestor_id=SYSTEM_ID, username="system")

    @classmethod
    def agent(cls) -> RequestContext:
        """Create a context for agent-initiated operations."""
        return cls(requestor_id=AGENT_ID, username="agent")
