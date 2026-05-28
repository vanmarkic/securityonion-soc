"""Tests for the /api/assistant/ routes — ported from Go assistanthandler_test.go."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.assistant_routes import (
    get_assistant_service,
    get_request_context_dep,
    router as assistant_router,
)
from src.domain.assistant import (
    AssistantSession,
    BalanceResponse,
    ContentBlock,
    GetSessionsQuery,
    HealthResponse,
    Message,
    StoredMessage,
    ToolResponse,
    ToolResult,
    ToolResultContent,
    UserUsage,
)
from src.services.assistant_service import AssistantService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Fake Assistantstore
# ---------------------------------------------------------------------------

class FakeAssistantstore:
    """In-memory stub implementing the Assistantstore protocol for tests."""

    def __init__(self) -> None:
        self.saved_messages: list[StoredMessage] = []
        self.created_sessions: list[AssistantSession] = []
        self.deleted_session_ids: list[str] = []
        self.updated_tags: dict[str, list[str]] = {}

        # Configurable return values
        self.history_to_return: list[StoredMessage] = []
        self.sessions_to_return: list[AssistantSession] = []
        self.usage_to_return: list[UserUsage] = []
        self.error: Exception | None = None
        self.history_error: Exception | None = None

    async def save_chat(self, message: StoredMessage) -> None:
        if self.error:
            raise self.error
        self.saved_messages.append(message)

    async def get_chat_history(self, session_id: str) -> list[StoredMessage]:
        if self.history_error:
            raise self.history_error
        if self.error:
            raise self.error
        return self.history_to_return

    async def get_sessions(self, query: GetSessionsQuery) -> list[AssistantSession]:
        if self.error:
            raise self.error
        return self.sessions_to_return

    async def create_session(self, session: AssistantSession) -> None:
        if self.error:
            raise self.error
        self.created_sessions.append(session)

    async def update_session_tags(self, session_id: str, tags: list[str]) -> None:
        if self.error:
            raise self.error
        self.updated_tags[session_id] = tags

    async def delete_session(self, session_id: str) -> None:
        if self.error:
            raise self.error
        self.deleted_session_ids.append(session_id)

    async def get_usage(
        self, start: datetime, end: datetime,
    ) -> list[UserUsage]:
        if self.error:
            raise self.error
        return self.usage_to_return


# ---------------------------------------------------------------------------
# Fake AssistantManager
# ---------------------------------------------------------------------------

class FakeAssistantManager:
    """In-memory stub implementing the AssistantManager protocol for tests."""

    def __init__(self) -> None:
        self.chat_response: list[Message] = []
        self.stream_chunks: list[dict] = []
        self.tool_response: ToolResponse | None = None
        self.balance_response: BalanceResponse = BalanceResponse()
        self.health_response: HealthResponse | None = HealthResponse(status="healthy")
        self.chat_error: Exception | None = None
        self.tool_error: Exception | None = None
        self.balance_error: Exception | None = None
        self.health_error: Exception | None = None

        # Capture calls
        self.chat_calls: list[tuple[str, list[Message]]] = []
        self.tool_calls: list[tuple[str, str, str]] = []

    async def chat(
        self, model: str, messages: list[Message],
    ) -> list[Message]:
        self.chat_calls.append((model, messages))
        if self.chat_error:
            raise self.chat_error
        return self.chat_response

    async def chat_stream(
        self, model: str, messages: list[Message],
    ) -> AsyncIterator[dict]:
        self.chat_calls.append((model, messages))
        if self.chat_error:
            raise self.chat_error

        async def _gen() -> AsyncIterator[dict]:
            for chunk in self.stream_chunks:
                yield chunk

        return _gen()

    async def execute_tool(
        self, tool_name: str, params: str, aux_data: str,
    ) -> ToolResponse:
        self.tool_calls.append((tool_name, params, aux_data))
        if self.tool_error:
            raise self.tool_error
        if self.tool_response is None:
            raise ValueError("no tool response configured")
        return self.tool_response

    async def balance(self, model: str) -> BalanceResponse:
        if self.balance_error:
            raise self.balance_error
        return self.balance_response

    async def health(self, model: str) -> HealthResponse:
        if self.health_error:
            raise self.health_error
        if self.health_response is None:
            return HealthResponse()
        return self.health_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(
    fake_store: FakeAssistantstore,
    fake_manager: FakeAssistantManager,
    airgap_enabled: bool = False,
) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake dependencies."""
    test_app = FastAPI()
    test_app.include_router(assistant_router, prefix="/api")

    service = AssistantService(
        store=fake_store,
        manager=fake_manager,
        airgap_enabled=airgap_enabled,
    )
    test_app.dependency_overrides[get_assistant_service] = lambda: service
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="test-user-123",
        username="test",
    )
    return test_app


@pytest.fixture
def fake_store() -> FakeAssistantstore:
    return FakeAssistantstore()


@pytest.fixture
def fake_manager() -> FakeAssistantManager:
    return FakeAssistantManager()


@pytest.fixture
async def client(fake_store: FakeAssistantstore, fake_manager: FakeAssistantManager):
    test_app = _make_app(fake_store, fake_manager)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def airgap_client(fake_store: FakeAssistantstore, fake_manager: FakeAssistantManager):
    test_app = _make_app(fake_store, fake_manager, airgap_enabled=True)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# POST /assistant/chat — non-streaming
# ===========================================================================

class TestPostChat:
    async def test_chat_with_existing_session(self, client, fake_store, fake_manager):
        """Chat with an existing session (has history)."""
        session_id = "test-session-123"
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Hello, I need help")],
                ),
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[ContentBlock(type="text", text="How can I help?")],
                ),
            ),
        ]
        fake_manager.chat_response = [
            Message(
                role="assistant",
                content_blocks=[ContentBlock(type="text", text="Mock response with history")],
            ),
        ]

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "What is my current balance?", "sessionId": session_id, "model": "test-model"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["role"] == "assistant"

        # Should have captured 3 messages: 2 history + 1 new
        model, messages = fake_manager.chat_calls[0]
        assert model == "test-model"
        assert len(messages) == 3
        assert messages[2].content_blocks[0].text == "What is my current balance?"

        # Should NOT create a new session (has history)
        assert len(fake_store.created_sessions) == 0

        # Should save user message + assistant response = 2
        assert len(fake_store.saved_messages) == 2

    async def test_chat_new_session(self, client, fake_store, fake_manager):
        """Chat without session history creates a new session."""
        fake_store.history_to_return = []
        fake_manager.chat_response = [
            Message(
                role="assistant",
                content_blocks=[ContentBlock(type="text", text="Mock response")],
            ),
        ]

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "Hello", "model": "test-model"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

        # New session should have been created
        assert len(fake_store.created_sessions) == 1
        assert fake_store.created_sessions[0].title == "Hello"

        # Only 1 user message from chat (no history), manager gets it
        model, messages = fake_manager.chat_calls[0]
        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content_blocks[0].text == "Hello"

    async def test_chat_request_too_large(self, client, fake_store, fake_manager):
        """Chat that triggers REQUEST_TOO_LARGE returns 400."""
        fake_store.history_to_return = []
        fake_manager.chat_error = Exception("ERROR_ASSISTANT_REQUEST_TOO_LARGE")

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "Huge message", "model": "test-model"},
        )
        assert resp.status_code == 400

    async def test_chat_upstream_error(self, client, fake_store, fake_manager):
        """Chat that triggers generic error returns 500."""
        fake_store.history_to_return = []
        fake_manager.chat_error = Exception("some error")

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "Hello", "model": "test-model"},
        )
        assert resp.status_code == 500

    async def test_chat_airgap_mode(self, airgap_client):
        """Chat in airgap mode returns 500."""
        resp = await airgap_client.post(
            "/api/assistant/chat",
            json={"msg": "Hello", "model": "test-model"},
        )
        assert resp.status_code == 500
        assert "ERROR_SERVICE_NOT_AVAILABLE" in resp.json()["detail"]


# ===========================================================================
# POST /assistant/chat — streaming
# ===========================================================================

class TestPostChatStreaming:
    async def test_chat_streaming(self, client, fake_store, fake_manager):
        """Streaming chat returns SSE response."""
        fake_store.history_to_return = []
        fake_manager.stream_chunks = [
            {"type": "content_block_delta", "delta": {"text": "Hello"}},
            {"type": "message_stop"},
        ]

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "Hi there", "model": "test-model"},
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body = resp.text
        assert "data: " in body
        assert "[DONE]" in body

    async def test_chat_streaming_new_session(self, client, fake_store, fake_manager):
        """Streaming chat creates a new session when none exists."""
        fake_store.history_to_return = []
        fake_manager.stream_chunks = [
            {"type": "message_start", "message": {"role": "assistant"}},
        ]

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "Stream me", "model": "test-model"},
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert len(fake_store.created_sessions) == 1


# ===========================================================================
# POST /assistant/chat — entity association
# ===========================================================================

class TestPostChatWithEntity:
    async def test_chat_with_entity_type_and_id(self, client, fake_store, fake_manager):
        """Chat with entityType and entityId creates session with those fields."""
        fake_store.history_to_return = []
        fake_manager.chat_response = [
            Message(
                role="assistant",
                content_blocks=[ContentBlock(type="text", text="Investigating alert")],
            ),
        ]

        resp = await client.post(
            "/api/assistant/chat?entityType=alert_investigation&entityId=alert-123",
            json={"msg": "Investigate this alert", "model": "test-model"},
        )
        assert resp.status_code == 200
        assert len(fake_store.created_sessions) == 1
        session = fake_store.created_sessions[0]
        assert session.type == "alert_investigation"
        assert session.entity_id == "alert-123"


# ===========================================================================
# POST /assistant/tool/{name} — non-streaming
# ===========================================================================

class TestPostTool:
    async def test_tool_execution_success(self, client, fake_store, fake_manager):
        """Successful tool execution returns chat response."""
        session_id = "test-session-123"
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Get me some events")],
                ),
            ),
        ]
        fake_manager.tool_response = ToolResponse(
            tool_name="query_events",
            result={"events": ["event1", "event2"]},
        )
        fake_manager.chat_response = [
            Message(
                role="assistant",
                content_blocks=[ContentBlock(type="text", text="I found 2 events.")],
            ),
        ]

        resp = await client.post(
            "/api/assistant/tool/query_events",
            json={
                "sessionId": session_id,
                "toolUseId": "tooluse_test_123",
                "params": {"query": "test query"},
                "model": "test-model",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["role"] == "assistant"

        # Verify tool was executed
        assert len(fake_manager.tool_calls) == 1
        assert fake_manager.tool_calls[0][0] == "query_events"

        # Verify messages were saved (tool result + assistant response)
        assert len(fake_store.saved_messages) == 2
        tool_saved = fake_store.saved_messages[0]
        assert tool_saved.tags == ["tool_result"]
        assert tool_saved.message.role == "user"
        assert tool_saved.message.content_blocks[0].tool_result is not None
        assert tool_saved.message.content_blocks[0].tool_result.tool_use_id == "tooluse_test_123"
        assert not tool_saved.message.content_blocks[0].tool_result.is_error

    async def test_tool_execution_error(self, client, fake_store, fake_manager):
        """Tool execution error wraps as error tool result."""
        session_id = "test-session-123"
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Do something")],
                ),
            ),
        ]
        fake_manager.tool_error = Exception("tool failed")
        fake_manager.chat_response = [
            Message(
                role="assistant",
                content_blocks=[ContentBlock(type="text", text="Tool failed.")],
            ),
        ]

        resp = await client.post(
            "/api/assistant/tool/bad_tool",
            json={
                "sessionId": session_id,
                "toolUseId": "tooluse_err",
                "params": {},
                "model": "test-model",
            },
        )
        assert resp.status_code == 200

        # Verify the tool result was saved as an error
        tool_saved = fake_store.saved_messages[0]
        assert tool_saved.message.content_blocks[0].tool_result.is_error
        assert tool_saved.message.content_blocks[0].tool_result.status == "error"

    async def test_tool_airgap_mode(self, airgap_client):
        """Tool in airgap mode returns 500."""
        resp = await airgap_client.post(
            "/api/assistant/tool/test",
            json={"sessionId": "s1", "toolUseId": "t1", "params": {}, "model": "m"},
        )
        assert resp.status_code == 500


# ===========================================================================
# POST /assistant/tool/{name} — streaming
# ===========================================================================

class TestPostToolStreaming:
    async def test_tool_streaming(self, client, fake_store, fake_manager):
        """Tool execution with streaming."""
        session_id = "test-session-123"
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Do thing")],
                ),
            ),
        ]
        fake_manager.tool_response = ToolResponse(
            tool_name="query_events",
            result={"events": []},
        )
        fake_manager.stream_chunks = [
            {"type": "content_block_delta", "delta": {"text": "Streaming result"}},
        ]

        resp = await client.post(
            "/api/assistant/tool/query_events",
            json={
                "sessionId": session_id,
                "toolUseId": "tooluse_stream",
                "params": {"query": "test"},
                "model": "test-model",
            },
            headers={"Accept": "text/event-stream"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")


# ===========================================================================
# GET /assistant/balance/{model_and_adapter}
# ===========================================================================

class TestGetBalance:
    async def test_balance_success(self, client, fake_manager):
        """Successful balance check returns balance and health."""
        fake_manager.health_response = HealthResponse(status="healthy")
        fake_manager.balance_response = BalanceResponse(balance=10000)

        resp = await client.get("/api/assistant/balance/test-model")
        assert resp.status_code == 200
        data = resp.json()
        assert data["credit_balance"] == 10000
        assert data["health_status"] == "healthy"

    async def test_balance_unhealthy(self, client, fake_manager):
        """Health check failure returns 500."""
        fake_manager.health_error = Exception("service unreachable")

        resp = await client.get("/api/assistant/balance/test-model")
        assert resp.status_code == 500

    async def test_balance_nil_health(self, client, fake_manager):
        """Nil health response returns 500."""
        fake_manager.health_response = HealthResponse(status="")

        resp = await client.get("/api/assistant/balance/test-model")
        assert resp.status_code == 500

    async def test_balance_airgap(self, airgap_client):
        """Balance in airgap mode returns 500."""
        resp = await airgap_client.get("/api/assistant/balance/test-model")
        assert resp.status_code == 500

    async def test_balance_with_slashes_in_model(self, client, fake_manager):
        """Model name with slashes (e.g. qwen/qwen2.5-small@adapter)."""
        fake_manager.health_response = HealthResponse(status="healthy")
        fake_manager.balance_response = BalanceResponse(balance=5000)

        resp = await client.get("/api/assistant/balance/qwen/qwen2.5-small@MyAdapter")
        assert resp.status_code == 200
        data = resp.json()
        assert data["credit_balance"] == 5000


# ===========================================================================
# GET /assistant/sessions
# ===========================================================================

class TestGetSessions:
    async def test_list_sessions(self, client, fake_store):
        """List sessions returns session metadata."""
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id="s1",
                title="First session",
                tags=["investigation"],
                user_id="test-user-123",
            ),
            AssistantSession(
                session_id="s2",
                title="Second session",
                tags=[],
                user_id="test-user-123",
            ),
        ]

        resp = await client.get("/api/assistant/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["sessionId"] == "s1"
        assert data[1]["sessionId"] == "s2"

    async def test_list_sessions_empty(self, client, fake_store):
        """List sessions returns empty array when none exist."""
        fake_store.sessions_to_return = []

        resp = await client.get("/api/assistant/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_sessions_store_error(self, client, fake_store):
        """Store error returns 500."""
        fake_store.error = Exception("db error")

        resp = await client.get("/api/assistant/sessions")
        assert resp.status_code == 500


# ===========================================================================
# GET /assistant/sessions/{sessionId} — session details
# ===========================================================================

class TestGetSessionDetails:
    async def test_get_session_details_success(self, client, fake_store):
        """Get session details returns session + history."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id=session_id,
                title="Test Session",
                user_id="test-user-123",
            ),
        ]
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Hello?")],
                ),
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[ContentBlock(type="text", text="Hi!")],
                ),
            ),
        ]

        resp = await client.get(f"/api/assistant/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["sessionId"] == session_id
        assert len(data["history"]) == 2

    async def test_get_session_details_not_found(self, client, fake_store):
        """Non-existent session returns empty details (matching Go behavior)."""
        fake_store.sessions_to_return = []

        resp = await client.get("/api/assistant/sessions/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        # Both session and history should be absent/null
        assert "session" not in data or data.get("session") is None

    async def test_get_session_details_removes_thought_signature(
        self, client, fake_store,
    ):
        """Thought signatures are stripped from history."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(session_id=session_id, title="Test"),
        ]
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[
                        ContentBlock(
                            type="tool_use",
                            name="test_tool",
                            thought_signature="secret_sig",
                        ),
                    ],
                ),
            ),
        ]

        resp = await client.get(f"/api/assistant/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        history = data["history"]
        for msg in history:
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    assert "thought_signature" not in block

    async def test_get_session_details_store_error(self, client, fake_store):
        """Store error returns 500."""
        fake_store.error = Exception("db error")

        resp = await client.get("/api/assistant/sessions/test-session")
        assert resp.status_code == 500


# ===========================================================================
# PUT /assistant/sessions/{sessionId} — update session
# ===========================================================================

class TestUpdateSession:
    async def test_add_tag(self, client, fake_store):
        """Add tag to session succeeds."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id=session_id,
                title="Test Session",
                tags=["existing-tag"],
                user_id="test-user-123",
            ),
        ]

        resp = await client.put(
            f"/api/assistant/sessions/{session_id}",
            json={"action": "add", "tag": "case-1234"},
        )
        assert resp.status_code == 204
        assert fake_store.updated_tags[session_id] == ["existing-tag", "case-1234"]

    async def test_add_duplicate_tag(self, client, fake_store):
        """Adding a tag that already exists returns 409."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id=session_id,
                title="Test Session",
                tags=["existing-tag"],
            ),
        ]

        resp = await client.put(
            f"/api/assistant/sessions/{session_id}",
            json={"action": "add", "tag": "existing-tag"},
        )
        assert resp.status_code == 409

    async def test_remove_tag(self, client, fake_store):
        """Remove tag from session succeeds."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id=session_id,
                title="Test Session",
                tags=["case-1234", "other-tag"],
            ),
        ]

        resp = await client.put(
            f"/api/assistant/sessions/{session_id}",
            json={"action": "remove", "tag": "case-1234"},
        )
        assert resp.status_code == 204
        assert fake_store.updated_tags[session_id] == ["other-tag"]

    async def test_remove_nonexistent_tag(self, client, fake_store):
        """Removing a tag that doesn't exist returns 409."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id=session_id,
                title="Test Session",
                tags=["other-tag"],
            ),
        ]

        resp = await client.put(
            f"/api/assistant/sessions/{session_id}",
            json={"action": "remove", "tag": "missing-tag"},
        )
        assert resp.status_code == 409

    async def test_update_session_not_found(self, client, fake_store):
        """Updating non-existent session returns 404."""
        fake_store.sessions_to_return = []

        resp = await client.put(
            "/api/assistant/sessions/nonexistent",
            json={"action": "add", "tag": "case-1234"},
        )
        assert resp.status_code == 404

    async def test_update_session_store_error(self, client, fake_store):
        """Store error returns 500."""
        fake_store.error = Exception("db error")

        resp = await client.put(
            "/api/assistant/sessions/test-session",
            json={"action": "add", "tag": "case-1234"},
        )
        assert resp.status_code == 500


# ===========================================================================
# DELETE /assistant/sessions/{sessionId}
# ===========================================================================

class TestDeleteSession:
    async def test_delete_session_success(self, client, fake_store):
        """Delete session succeeds."""
        session_id = "test-session-123"

        resp = await client.delete(f"/api/assistant/sessions/{session_id}")
        assert resp.status_code == 204
        assert session_id in fake_store.deleted_session_ids

    async def test_delete_session_store_error(self, client, fake_store):
        """Store error returns 500."""
        fake_store.error = Exception("db error")

        resp = await client.delete("/api/assistant/sessions/test-session")
        assert resp.status_code == 500


# ===========================================================================
# GET /assistant/admin/stats — usage statistics
# ===========================================================================

class TestGetUsage:
    async def test_get_usage_success(self, client, fake_store):
        """Get usage returns user usage stats."""
        fake_store.usage_to_return = [
            UserUsage(
                user_id="user-1",
                total_input_tokens=1000,
                total_output_tokens=2000,
                total_credits=150,
                total_messages=100,
                total_sessions=10,
            ),
            UserUsage(
                user_id="user-2",
                total_input_tokens=500,
                total_output_tokens=1000,
                total_credits=75,
                total_messages=5,
                total_sessions=1,
            ),
        ]

        resp = await client.get(
            "/api/assistant/admin/stats",
            params={
                "range": "2025-01-01 00:00:00 - 2025-01-31 23:59:59",
                "format": "%Y-%m-%d %H:%M:%S",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["userId"] == "user-1"
        assert data[1]["userId"] == "user-2"

    async def test_get_usage_store_error(self, client, fake_store):
        """Store error returns 500."""
        fake_store.error = Exception("db error")

        resp = await client.get(
            "/api/assistant/admin/stats",
            params={
                "range": "2025-01-01 00:00:00 - 2025-01-31 23:59:59",
                "format": "%Y-%m-%d %H:%M:%S",
            },
        )
        assert resp.status_code == 500

    async def test_get_usage_bad_date_range(self, client):
        """Invalid date range returns 400."""
        resp = await client.get(
            "/api/assistant/admin/stats",
            params={"range": "bad-date", "format": "%Y-%m-%d %H:%M:%S"},
        )
        assert resp.status_code == 400


# ===========================================================================
# GET /assistant/admin/sessions — all sessions
# ===========================================================================

class TestGetAllSessions:
    async def test_get_all_sessions(self, client, fake_store):
        """Get all sessions returns session list."""
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id="s1",
                title="Session 1",
                user_id="user-1",
            ),
            AssistantSession(
                session_id="s2",
                title="Session 2",
                user_id="user-2",
            ),
        ]

        resp = await client.get(
            "/api/assistant/admin/sessions",
            params={
                "range": "2025-01-01 00:00:00 - 2025-12-31 23:59:59",
                "format": "%Y-%m-%d %H:%M:%S",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_get_all_sessions_store_error(self, client, fake_store):
        """Store error returns 500."""
        fake_store.error = Exception("db error")

        resp = await client.get(
            "/api/assistant/admin/sessions",
            params={
                "range": "2025-01-01 00:00:00 - 2025-12-31 23:59:59",
                "format": "%Y-%m-%d %H:%M:%S",
            },
        )
        assert resp.status_code == 500


# ===========================================================================
# GET /assistant/admin/{userId}/sessions — user sessions
# ===========================================================================

class TestGetUserSessions:
    async def test_get_user_sessions(self, client, fake_store):
        """Get sessions for a specific user."""
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id="s1",
                title="User session",
                user_id="user-1",
            ),
        ]

        resp = await client.get(
            "/api/assistant/admin/user-1/sessions",
            params={
                "range": "2025-01-01 00:00:00 - 2025-12-31 23:59:59",
                "format": "%Y-%m-%d %H:%M:%S",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1


# ===========================================================================
# GET /assistant/admin/{userId}/sessions/{sessionId}/history
# ===========================================================================

class TestManageSessionHistory:
    async def test_get_session_history_admin(self, client, fake_store):
        """Admin can get session history for a user."""
        user_id = "test-user-123"
        session_id = "test-session-456"
        fake_store.sessions_to_return = [
            AssistantSession(
                session_id=session_id,
                user_id=user_id,
            ),
        ]
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="What are my alerts?")],
                ),
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[ContentBlock(type="text", text="Checking alerts...")],
                ),
            ),
        ]

        resp = await client.get(
            f"/api/assistant/admin/{user_id}/sessions/{session_id}/history",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_get_session_history_admin_not_found(self, client, fake_store):
        """Non-existent session returns 404."""
        fake_store.sessions_to_return = []

        resp = await client.get(
            "/api/assistant/admin/user-1/sessions/nonexistent/history",
        )
        assert resp.status_code == 404

    async def test_get_session_history_admin_store_error(self, client, fake_store):
        """Store error returns 500."""
        fake_store.error = Exception("db error")

        resp = await client.get(
            "/api/assistant/admin/user-1/sessions/session-1/history",
        )
        assert resp.status_code == 500


# ===========================================================================
# Context compression (historyToContext)
# ===========================================================================

class TestHistoryToContext:
    """Tests for the _history_to_context helper via the service layer."""

    async def test_simple_history_no_compression(self, client, fake_store, fake_manager):
        """Simple history without compression passes all messages."""
        session_id = "s1"
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Hello")],
                ),
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[ContentBlock(type="text", text="Hi there!")],
                ),
            ),
        ]
        fake_manager.chat_response = [
            Message(role="assistant", content_blocks=[ContentBlock(type="text", text="OK")]),
        ]

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "New msg", "sessionId": session_id, "model": "m"},
        )
        assert resp.status_code == 200

        model, messages = fake_manager.chat_calls[0]
        assert len(messages) == 3  # 2 history + 1 new

    async def test_compressed_history(self, client, fake_store, fake_manager):
        """Compressed history drops older messages."""
        session_id = "s1"
        fake_store.history_to_return = [
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Old message 1")],
                ),
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[ContentBlock(type="text", text="Old response")],
                ),
                tags=["something_else"],
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Long message")],
                ),
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[ContentBlock(type="text", text="Long response")],
                ),
            ),
            # Compression point — older messages should be dropped
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="user",
                    content_blocks=[ContentBlock(type="text", text="Compress it")],
                ),
                tags=["context_compression"],
            ),
            StoredMessage(
                session_id=session_id,
                message=Message(
                    role="assistant",
                    content_blocks=[ContentBlock(type="text", text="Less data")],
                ),
            ),
        ]
        fake_manager.chat_response = [
            Message(role="assistant", content_blocks=[ContentBlock(type="text", text="OK")]),
        ]

        resp = await client.post(
            "/api/assistant/chat",
            json={"msg": "After compression", "sessionId": session_id, "model": "m"},
        )
        assert resp.status_code == 200

        model, messages = fake_manager.chat_calls[0]
        # Only "Compress it", "Less data", and the new message
        assert len(messages) == 3
        assert messages[0].content_blocks[0].text == "Compress it"
        assert messages[1].content_blocks[0].text == "Less data"
        assert messages[2].content_blocks[0].text == "After compression"


# ===========================================================================
# Shared sessions (via tags)
# ===========================================================================

class TestSharedSessions:
    async def test_add_shared_tag(self, client, fake_store):
        """Add 'shared' tag to a session."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(session_id=session_id, tags=[]),
        ]

        resp = await client.put(
            f"/api/assistant/sessions/{session_id}",
            json={"action": "add", "tag": "shared"},
        )
        assert resp.status_code == 204
        assert fake_store.updated_tags[session_id] == ["shared"]

    async def test_remove_shared_tag(self, client, fake_store):
        """Remove 'shared' tag from a session."""
        session_id = "test-session-123"
        fake_store.sessions_to_return = [
            AssistantSession(session_id=session_id, tags=["shared"]),
        ]

        resp = await client.put(
            f"/api/assistant/sessions/{session_id}",
            json={"action": "remove", "tag": "shared"},
        )
        assert resp.status_code == 204
        assert fake_store.updated_tags[session_id] == []


# ===========================================================================
# Date range parsing
# ===========================================================================

class TestDateRangeParsing:
    async def test_valid_date_range(self, client, fake_store):
        """Valid date range parses correctly."""
        fake_store.usage_to_return = []

        resp = await client.get(
            "/api/assistant/admin/stats",
            params={
                "range": "2025-01-01 00:00:00 - 2025-01-31 23:59:59",
                "format": "%Y-%m-%d %H:%M:%S",
            },
        )
        assert resp.status_code == 200

    async def test_invalid_date_range_format(self, client):
        """Invalid date range format returns 400."""
        resp = await client.get(
            "/api/assistant/admin/stats",
            params={"range": "not-a-date", "format": "%Y-%m-%d %H:%M:%S"},
        )
        assert resp.status_code == 400

    async def test_default_date_range(self, client, fake_store):
        """Missing range defaults to wide range."""
        fake_store.usage_to_return = []

        resp = await client.get("/api/assistant/admin/stats")
        assert resp.status_code == 200


# ===========================================================================
# Message serialization
# ===========================================================================

class TestMessageSerialization:
    def test_message_with_content_str(self):
        """Message with content_str serializes content as string."""
        msg = Message(role="user", content_str="hello")
        data = msg.model_dump()
        assert data["content"] == "hello"
        assert data["role"] == "user"

    def test_message_with_content_blocks(self):
        """Message with content_blocks serializes content as array."""
        msg = Message(
            role="assistant",
            content_blocks=[
                ContentBlock(type="text", text="Hello world"),
            ],
        )
        data = msg.model_dump()
        assert isinstance(data["content"], list)
        assert len(data["content"]) == 1
        assert data["content"][0]["type"] == "text"
        assert data["content"][0]["text"] == "Hello world"

    def test_message_with_usage(self):
        """Message with usage includes usage data."""
        from src.domain.assistant import Usage

        msg = Message(
            role="assistant",
            content_blocks=[ContentBlock(type="text", text="Hi")],
            stop_reason="end_turn",
            usage=Usage(input_tokens=100, output_tokens=50, credits=200),
        )
        data = msg.model_dump()
        assert data["stop_reason"] == "end_turn"
        assert data["usage"]["input_tokens"] == 100
        assert data["usage"]["output_tokens"] == 50
        assert data["usage"]["credits"] == 200


# ===========================================================================
# StoredMessage / PrepareForStorage
# ===========================================================================

class TestPrepareForStorage:
    def test_prepare_for_storage(self):
        """PrepareForStorage creates correct StoredMessage."""
        msg = Message(
            role="user",
            content_blocks=[ContentBlock(type="text", text="Test")],
        )
        stored = msg.prepare_for_storage("session-1", ["tag1", "tag2"], "model-1")
        assert stored.session_id == "session-1"
        assert stored.tags == ["tag1", "tag2"]
        assert stored.model == "model-1"
        assert stored.message is msg

    def test_prepare_for_storage_none_tags(self):
        """PrepareForStorage with None tags uses empty list."""
        msg = Message(role="assistant", content_blocks=[])
        stored = msg.prepare_for_storage("session-1", None, "model-1")
        assert stored.tags == []
