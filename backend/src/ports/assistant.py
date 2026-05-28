"""Assistant ports — defines contracts for assistant persistence and AI manager."""

from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, Protocol, runtime_checkable

from src.domain.assistant import (
    AssistantSession,
    BalanceResponse,
    GetSessionsQuery,
    HealthResponse,
    Message,
    StoredMessage,
    ToolResponse,
    UserUsage,
)


@runtime_checkable
class Assistantstore(Protocol):
    """Protocol that any assistant-storing adapter must satisfy."""

    async def save_chat(self, message: StoredMessage) -> None: ...

    async def get_chat_history(self, session_id: str) -> list[StoredMessage]: ...

    async def get_sessions(self, query: GetSessionsQuery) -> list[AssistantSession]: ...

    async def create_session(self, session: AssistantSession) -> None: ...

    async def update_session_tags(self, session_id: str, tags: list[str]) -> None: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def get_usage(
        self, start: datetime, end: datetime,
    ) -> list[UserUsage]: ...


@runtime_checkable
class AssistantManager(Protocol):
    """Protocol that any AI assistant manager must satisfy."""

    async def chat(
        self, model: str, messages: list[Message],
    ) -> list[Message]: ...

    async def chat_stream(
        self, model: str, messages: list[Message],
    ) -> AsyncIterator[dict]: ...

    async def execute_tool(
        self, tool_name: str, params: str, aux_data: str,
    ) -> ToolResponse: ...

    async def balance(self, model: str) -> BalanceResponse: ...

    async def health(self, model: str) -> HealthResponse: ...
