"""Auth middleware — FastAPI dependency that extracts RequestContext from headers."""

from __future__ import annotations

from fastapi import Request

from src.shared.context import AGENT_ID, RequestContext


async def get_request_context(request: Request) -> RequestContext:
    """Extract auth identity from request headers.

    Falls back to agent context when headers are absent.
    """
    user_id = request.headers.get("X-User-Id", AGENT_ID)
    username = request.headers.get("X-Username", "agent")
    return RequestContext(requestor_id=user_id, username=username)
