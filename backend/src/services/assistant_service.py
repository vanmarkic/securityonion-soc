"""AssistantService — business logic for assistant operations."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from src.domain.assistant import (
    MESSAGE_TAG_CONTEXT_COMPRESSION,
    AssistantSession,
    AssistantSessionDetails,
    ContentBlock,
    GetSessionsQuery,
    IncomingMessage,
    Message,
    StoredMessage,
    ToolRequest,
    ToolResponse,
    ToolResult,
    ToolResultContent,
    UpdateSessionRequest,
)
from src.ports.assistant import AssistantManager, Assistantstore

logger = logging.getLogger(__name__)


def _history_to_context(history: list[StoredMessage]) -> list[Message]:
    """Convert stored message history to context messages for the AI.

    If a context_compression tag is found, drop all older messages.
    """
    messages: list[Message] = []
    for msg in history:
        if MESSAGE_TAG_CONTEXT_COMPRESSION in (msg.tags or []):
            messages.clear()
        if msg.message is not None:
            messages.append(msg.message)
    return messages


class AssistantService:
    """Business logic for all assistant-related endpoints."""

    def __init__(
        self,
        store: Assistantstore,
        manager: AssistantManager,
        airgap_enabled: bool = False,
    ) -> None:
        self._store = store
        self._manager = manager
        self._airgap_enabled = airgap_enabled

    @property
    def airgap_enabled(self) -> bool:
        return self._airgap_enabled

    # -- Chat (non-streaming) --

    async def chat(
        self,
        incoming: IncomingMessage,
        user_id: str,
        entity_type: str = "",
        entity_id: str = "",
    ) -> list[dict[str, Any]]:
        """Process a non-streaming chat request."""
        session_id = incoming.session_id or str(uuid.uuid4())

        history = await self._get_history_safe(session_id)
        is_new_session = len(history) == 0

        messages = _history_to_context(history)
        new_msg = Message(
            role="user",
            content_blocks=[ContentBlock(type="text", text=incoming.msg)],
        )
        messages.append(new_msg)

        response = await self._manager.chat(incoming.model, messages)

        if is_new_session:
            session = AssistantSession(
                session_id=session_id,
                title=incoming.msg,
                type=entity_type if entity_type and entity_id else "",
                entity_id=entity_id if entity_type and entity_id else "",
            )
            await self._store.create_session(session)

        await self._store.save_chat(
            new_msg.prepare_for_storage(session_id, incoming.tags, incoming.model),
        )

        for msg in response:
            await self._store.save_chat(
                msg.prepare_for_storage(session_id, None, incoming.model),
            )

        return [msg.model_dump() for msg in response]

    # -- Chat (streaming) --

    async def chat_stream(
        self,
        incoming: IncomingMessage,
        user_id: str,
        entity_type: str = "",
        entity_id: str = "",
    ) -> AsyncIterator[str]:
        """Process a streaming chat request, yielding SSE chunks."""
        session_id = incoming.session_id or str(uuid.uuid4())

        history = await self._get_history_safe(session_id)
        is_new_session = len(history) == 0

        messages = _history_to_context(history)
        new_msg = Message(
            role="user",
            content_blocks=[ContentBlock(type="text", text=incoming.msg)],
        )
        messages.append(new_msg)

        stream = await self._manager.chat_stream(incoming.model, messages)

        if is_new_session:
            session = AssistantSession(
                session_id=session_id,
                title=incoming.msg,
                type=entity_type if entity_type and entity_id else "",
                entity_id=entity_id if entity_type and entity_id else "",
            )
            await self._store.create_session(session)

        await self._store.save_chat(
            new_msg.prepare_for_storage(session_id, incoming.tags, incoming.model),
        )

        async for chunk in stream:
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    # -- Tool execution --

    async def execute_tool(
        self,
        tool_name: str,
        tool_req: ToolRequest,
        streaming: bool = False,
    ) -> list[dict[str, Any]] | AsyncIterator[str]:
        """Execute a tool and continue the conversation."""
        params_str = json.dumps(tool_req.params) if tool_req.params is not None else ""
        aux_data_str = json.dumps(tool_req.aux_data) if tool_req.aux_data is not None else ""

        result: ToolResponse | None = None
        tool_err: Exception | None = None
        try:
            result = await self._manager.execute_tool(tool_name, params_str, aux_data_str)
        except Exception as e:
            tool_err = e
            logger.error("unable to execute tool: %s", e)

        tool_result: ToolResult
        if tool_err is not None:
            tool_result = ToolResult(
                tool_use_id=tool_req.tool_use_id,
                status="error",
                is_error=True,
                content=[ToolResultContent(text=str(tool_err))],
            )
        else:
            res: Any = None
            if result is not None:
                res = {"result": result.result}
            tool_result = ToolResult(
                name=result.tool_name if result else "",
                tool_use_id=tool_req.tool_use_id,
                content=[ToolResultContent(json_data=res)],
            )

        tool_msg = Message(
            id=str(uuid.uuid4()),
            role="user",
            content_blocks=[ContentBlock(tool_result=tool_result)],
        )

        history = await self._store.get_chat_history(tool_req.session_id)
        messages = _history_to_context(history)
        messages.append(tool_msg)

        if not streaming:
            response = await self._manager.chat(tool_req.model, messages)

            await self._store.save_chat(
                tool_msg.prepare_for_storage(
                    tool_req.session_id, ["tool_result"], tool_req.model,
                ),
            )

            for msg in response:
                await self._store.save_chat(
                    msg.prepare_for_storage(tool_req.session_id, None, tool_req.model),
                )

            return [msg.model_dump() for msg in response]

        # Streaming tool response
        await self._store.save_chat(
            tool_msg.prepare_for_storage(
                tool_req.session_id, ["tool_result"], tool_req.model,
            ),
        )

        stream = await self._manager.chat_stream(tool_req.model, messages)

        async def _stream() -> AsyncIterator[str]:
            async for chunk in stream:
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return _stream()

    # -- Sessions CRUD --

    async def get_sessions(self, user_id: str) -> list[dict[str, Any]]:
        query = GetSessionsQuery(user_id=user_id)
        sessions = await self._store.get_sessions(query)
        return [s.model_dump(by_alias=True, exclude_none=True) for s in sessions]

    async def get_session_details(self, session_id: str) -> dict[str, Any]:
        query = GetSessionsQuery(
            session_id=session_id,
            include_deleted=True,
            with_usage=True,
        )
        sessions = await self._store.get_sessions(query)

        if not sessions:
            return AssistantSessionDetails().model_dump(by_alias=True, exclude_none=True)

        history = await self._store.get_chat_history(session_id)

        # Remove aux data (thought signatures)
        for msg in history:
            if msg.message is not None:
                for cb in msg.message.content_blocks:
                    cb.thought_signature = None

        details = AssistantSessionDetails(session=sessions[0], history=history)
        return details.model_dump(by_alias=True, exclude_none=True)

    async def update_session(
        self, session_id: str, request: UpdateSessionRequest,
    ) -> tuple[int, str | None]:
        """Update session tags. Returns (status_code, error_message)."""
        query = GetSessionsQuery(session_id=session_id)
        sessions = await self._store.get_sessions(query)

        if not sessions:
            return 404, "session not found"

        session = sessions[0]

        if request.action == "add":
            if request.tag in (session.tags or []):
                return 409, "tag already exists on session"
            session.tags = (session.tags or []) + [request.tag]
        elif request.action == "remove":
            if request.tag not in (session.tags or []):
                return 409, "session does not have tag"
            tags = list(session.tags or [])
            tags.remove(request.tag)
            session.tags = tags

        await self._store.update_session_tags(session_id, session.tags)
        return 204, None

    async def delete_session(self, session_id: str) -> None:
        await self._store.delete_session(session_id)

    # -- Admin endpoints --

    async def get_all_sessions(
        self,
        start: datetime,
        end: datetime,
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        query = GetSessionsQuery(
            user_id=user_id,
            include_deleted=True,
            with_usage=True,
            start=start,
            end=end,
        )
        sessions = await self._store.get_sessions(query)
        return [s.model_dump(by_alias=True, exclude_none=True) for s in sessions]

    async def get_session_history_admin(
        self, user_id: str, session_id: str,
    ) -> tuple[list[dict[str, Any]] | None, int, str | None]:
        """Get session history for admin. Returns (history, status, error)."""
        query = GetSessionsQuery(
            user_id=user_id,
            session_id=session_id,
            include_deleted=True,
        )
        sessions = await self._store.get_sessions(query)

        if not sessions:
            return None, 404, "no matching session found"

        history = await self._store.get_chat_history(session_id)
        return [m.model_dump(by_alias=True, exclude_none=True) for m in history], 200, None

    async def get_usage(
        self, start: datetime, end: datetime,
    ) -> list[dict[str, Any]]:
        usage = await self._store.get_usage(start, end)
        return [u.model_dump(by_alias=True, exclude_none=True) for u in usage]

    # -- Balance / Health --

    async def get_balance(self, model: str) -> dict[str, Any] | None:
        health = await self._manager.health(model)
        if health is None or not health.status:
            return None

        balance = await self._manager.balance(model)
        balance.health_status = health.status
        return balance.model_dump(by_alias=True, exclude_none=True)

    # -- Helpers --

    async def _get_history_safe(self, session_id: str) -> list[StoredMessage]:
        """Get chat history, returning empty list on not-found errors."""
        try:
            return await self._store.get_chat_history(session_id)
        except Exception as e:
            if "not found" in str(e):
                return []
            raise
