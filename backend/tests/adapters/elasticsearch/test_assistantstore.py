"""Unit tests for ElasticAssistantstore (Task 18 — sessions + chat history).

Ports the behavioral assertions of ``elasticassistantstore_test.go`` that fall
within the Assistantstore port surface for Task 18: chat validation, storage
shape (camelCase ``contentStr`` under ``so_chat.message``), session creation +
validation, soft-delete via ``update_by_query`` painless ``deleteTime``,
session filtering (``must_not exists deleteTime`` by default, term filters,
range), partial-malformed-hit skipping, ``get_chat_history`` ordering +
not-found contract, and owner-scoped ``update_session_tags``.

The async ES client is mocked with ``unittest.mock.AsyncMock`` (no live ES).
``get_sessions`` always issues the ``addMetaFromMessages`` msearch (Go calls it
unconditionally), so both ``es.search`` and ``es.msearch`` are mocked.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.adapters.elasticsearch.assistantstore import ElasticAssistantstore
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.domain.assistant import (
    AssistantSession,
    ContentBlock,
    GetSessionsQuery,
    Message,
    StoredMessage,
)


def _store(es: object) -> ElasticAssistantstore:
    return ElasticAssistantstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )


# Empty addMetaFromMessages response so get_sessions never errors on it.
_EMPTY_MSEARCH = {"took": 1, "responses": []}


# ----------------------------------------------------------------------
# save_chat
# ----------------------------------------------------------------------


async def test_save_chat_validates_session_id() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    msg = StoredMessage()
    msg.session_id = "ab"  # too short for validate_id (5-50)
    m = Message()
    m.content_str = "hi"
    msg.message = m
    with pytest.raises(Exception, match="invalid ID for SessionId"):
        await _store(es).save_chat(msg)
    es.index.assert_not_awaited()


async def test_save_chat_requires_exactly_one_content() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    msg = StoredMessage()
    msg.session_id = "session_12345"
    msg.message = Message()  # neither content_str nor content_blocks
    with pytest.raises(Exception, match="exactly one content type"):
        await _store(es).save_chat(msg)


async def test_save_chat_indexes_storage_shaped_doc() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.index.return_value = {"_id": "c1", "result": "created"}
    msg = StoredMessage()
    msg.session_id = "session_12345"
    m = Message()
    m.role = "user"
    m.content_str = "hello"
    msg.message = m
    await _store(es).save_chat(msg)

    doc = es.index.await_args.kwargs["document"]
    assert doc["so_kind"] == "chat"
    # storage shape: contentStr (NOT content), under so_chat.message
    assert doc["so_chat"]["message"]["contentStr"] == "hello"
    # requestor id stamped, id stripped before save
    assert doc["so_chat"]["userId"] == "u1"
    assert doc["so_chat"].get("id", "") == ""


async def test_save_chat_drops_empty_text_blocks() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.index.return_value = {"_id": "c1", "result": "created"}
    msg = StoredMessage()
    msg.session_id = "session_12345"
    m = Message()
    m.content_blocks = [
        ContentBlock(type="text", text=""),  # filtered out
        ContentBlock(type="text", text="keep"),
    ]
    msg.message = m
    await _store(es).save_chat(msg)

    msg_doc = es.index.await_args.kwargs["document"]["so_chat"]["message"]
    # storage shape: contentBlocks (NOT content); empty-text block dropped
    assert msg_doc["contentBlocks"] == [{"type": "text", "text": "keep"}]
    assert msg_doc["contentStr"] == ""


# ----------------------------------------------------------------------
# create_session
# ----------------------------------------------------------------------


async def test_create_session_validates_id() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    sess = AssistantSession(session_id="bad", title="T")
    with pytest.raises(Exception, match="invalid ID for SessionId"):
        await _store(es).create_session(sess)


async def test_create_session_requires_title() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    sess = AssistantSession(session_id="session_12345", title="")
    with pytest.raises(Exception, match="Title is too short"):
        await _store(es).create_session(sess)


async def test_create_session_indexes_storage_shaped_doc() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.index.return_value = {"_id": "s1", "result": "created"}
    sess = AssistantSession(session_id="session_12345", title="My Session")
    await _store(es).create_session(sess)

    doc = es.index.await_args.kwargs["document"]
    assert doc["so_kind"] == "session"
    assert doc["so_session"]["sessionId"] == "session_12345"
    assert doc["so_session"]["title"] == "My Session"
    assert doc["so_session"]["userId"] == "u1"


# ----------------------------------------------------------------------
# delete_session — soft delete
# ----------------------------------------------------------------------


async def test_delete_session_is_soft_delete_via_update_by_query() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    await _store(es).delete_session("session_12345")
    es.update_by_query.assert_awaited_once()
    body = es.update_by_query.await_args.kwargs
    assert "deleteTime" in body["script"]["source"]
    assert body["script"]["lang"] == "painless"
    # owner-scoped + sessionId-scoped term filters
    must = body["query"]["bool"]["must"]
    assert any("so_session.userId" in str(c) for c in must)
    assert any("session_12345" in str(c) for c in must)


# ----------------------------------------------------------------------
# update_session_tags
# ----------------------------------------------------------------------


async def test_update_session_tags_owner_scoped_painless() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    await _store(es).update_session_tags("session_12345", ["shared", "x"])
    es.update_by_query.assert_awaited_once()
    body = es.update_by_query.await_args.kwargs
    assert "so_session.tags = params.tags" in body["script"]["source"]
    assert body["script"]["params"]["tags"] == ["shared", "x"]
    must = body["query"]["bool"]["must"]
    assert any("so_session.userId" in str(c) for c in must)


# ----------------------------------------------------------------------
# get_sessions
# ----------------------------------------------------------------------


async def test_get_sessions_excludes_deleted_by_default() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False, "hits": {"total": 0, "hits": []},
    }
    es.msearch.return_value = _EMPTY_MSEARCH
    await _store(es).get_sessions(GetSessionsQuery(include_deleted=False))
    body = es.search.await_args.kwargs
    must_not = body["query"]["bool"]["must_not"]
    assert any("deleteTime" in str(c) for c in must_not)


async def test_get_sessions_include_deleted_has_no_must_not() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False, "hits": {"total": 0, "hits": []},
    }
    es.msearch.return_value = _EMPTY_MSEARCH
    await _store(es).get_sessions(GetSessionsQuery(include_deleted=True))
    body = es.search.await_args.kwargs
    assert "must_not" not in body["query"]["bool"]


async def test_get_sessions_user_and_session_filters() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False, "hits": {"total": 0, "hits": []},
    }
    es.msearch.return_value = _EMPTY_MSEARCH
    await _store(es).get_sessions(
        GetSessionsQuery(user_id="specific-user", session_id="sess-1"),
    )
    must = es.search.await_args.kwargs["query"]["bool"]["must"]
    flat = str(must)
    assert "so_session.userId" in flat and "specific-user" in flat
    assert "so_session.sessionId" in flat and "sess-1" in flat


async def test_get_sessions_range_filter() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False, "hits": {"total": 0, "hits": []},
    }
    es.msearch.return_value = _EMPTY_MSEARCH
    start = datetime(2020, 1, 2, 12, 0, 0, tzinfo=UTC)
    end = datetime(2020, 1, 3, 12, 0, 0, tzinfo=UTC)
    await _store(es).get_sessions(GetSessionsQuery(start=start, end=end))
    must = es.search.await_args.kwargs["query"]["bool"]["must"]
    ranges = [c for c in must if "range" in c]
    assert ranges
    ts = ranges[0]["range"]["@timestamp"]
    assert ts["gte"] == "2020-01-02T12:00:00Z"
    assert ts["lte"] == "2020-01-03T12:00:00Z"


async def test_get_sessions_sort_timestamp_asc_size_10000() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False, "hits": {"total": 0, "hits": []},
    }
    es.msearch.return_value = _EMPTY_MSEARCH
    await _store(es).get_sessions(GetSessionsQuery())
    body = es.search.await_args.kwargs
    assert body["size"] == 10000
    assert body["sort"] == [{"@timestamp": {"order": "asc"}}]


async def test_get_sessions_parses_hits_and_skips_malformed() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False,
        "hits": {"total": 3, "hits": [
            {"_id": "session1", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session1", "title": "Valid",
                               "userId": "u1"}}},
            {"_id": "session2", "_source": {"so_kind": "session"}},  # malformed
            {"_id": "session3", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session3", "title": "Also valid",
                               "userId": "u1"}}},
        ]},
    }
    es.msearch.return_value = {"took": 1, "responses": [{}, {}]}
    sessions = await _store(es).get_sessions(GetSessionsQuery())
    assert [s.session_id for s in sessions] == ["session1", "session3"]
    assert sessions[0].id == "session1"


async def test_add_meta_msearch_uses_full_cross_cluster_index() -> None:
    """msearch must target the un-stripped cross-cluster chat index.

    Go ``elasticassistantstore.go:906`` passes ``store.chatIndex`` directly
    (no ``disableCrossClusterIndex``), so ``update_time`` enrichment also covers
    chats on remote clusters. The default config index carries a ``*:`` prefix.
    """
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False,
        "hits": {"total": 1, "hits": [
            {"_id": "session1", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session1", "title": "Valid",
                               "userId": "u1"}}},
        ]},
    }
    es.msearch.return_value = _EMPTY_MSEARCH
    await _store(es).get_sessions(GetSessionsQuery())
    msearch_index = es.msearch.await_args.kwargs["index"]
    assert msearch_index == "*:so-assistant-chat"
    assert msearch_index.startswith("*:")  # cross-cluster prefix preserved


async def test_add_meta_sets_update_time_from_aggregation() -> None:
    """A session's update_time is populated from the max(createTime) agg."""
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False,
        "hits": {"total": 1, "hits": [
            {"_id": "session1", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session1", "title": "Valid",
                               "userId": "u1"}}},
        ]},
    }
    es.msearch.return_value = {"took": 1, "responses": [
        {"aggregations": {"update_time": {
            "value": 1577970000000.0,
            "value_as_string": "2020-01-02T12:00:00Z",
        }}},
    ]}
    sessions = await _store(es).get_sessions(GetSessionsQuery())
    assert sessions[0].update_time == datetime(2020, 1, 2, 12, 0, 0, tzinfo=UTC)


# ----------------------------------------------------------------------
# get_chat_history
# ----------------------------------------------------------------------


async def test_get_chat_history_not_found_when_no_session() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False, "hits": {"total": 0, "hits": []},
    }
    es.msearch.return_value = _EMPTY_MSEARCH
    with pytest.raises(Exception, match="Object not found"):
        await _store(es).get_chat_history("session_12345")


async def test_get_chat_history_returns_ordered_messages() -> None:
    from unittest.mock import AsyncMock

    es = AsyncMock()
    # 1st search: session existence check (GetSessions). 2nd: chat messages.
    es.search.side_effect = [
        {"took": 1, "timed_out": False, "hits": {"total": 1, "hits": [
            {"_id": "session1", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session1", "userId": "u1"}}}]}},
        {"took": 1, "timed_out": False, "hits": {"total": 2, "hits": [
            {"_id": "msg1", "_source": {
                "so_kind": "chat",
                "so_chat": {"sessionId": "session1", "userId": "u1",
                            "message": {"role": "user", "contentStr": "Hello"}}}},
            {"_id": "msg2", "_source": {
                "so_kind": "chat",
                "so_chat": {"sessionId": "session1", "userId": "u1",
                            "message": {"role": "assistant",
                                        "contentStr": "Hi there!"}}}},
        ]}},
    ]
    es.msearch.return_value = _EMPTY_MSEARCH
    messages = await _store(es).get_chat_history("session1")
    assert [m.id for m in messages] == ["msg1", "msg2"]
    assert messages[0].message is not None
    assert messages[0].message.content_str == "Hello"
    assert messages[1].message is not None
    assert messages[1].message.content_str == "Hi there!"


async def test_get_chat_history_session_check_includes_deleted() -> None:
    """GetChatHistory's session lookup must NOT filter deleted sessions."""
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.search.side_effect = [
        {"took": 1, "timed_out": False, "hits": {"total": 1, "hits": [
            {"_id": "session1", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session1", "userId": "u1"}}}]}},
        {"took": 1, "timed_out": False, "hits": {"total": 0, "hits": []}},
    ]
    es.msearch.return_value = _EMPTY_MSEARCH
    await _store(es).get_chat_history("session1")
    # first search is the session existence check; must NOT exclude deleted
    first_body = es.search.await_args_list[0].kwargs
    assert "must_not" not in first_body["query"]["bool"]
