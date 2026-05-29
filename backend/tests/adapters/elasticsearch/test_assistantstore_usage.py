"""Unit tests for ElasticAssistantstore usage aggregations (Task 19).

Ports the behavioral assertions of ``elasticassistantstore_test.go``'s
``TestPopulateSessionUsage_*``, ``TestGetSessions_WithUsage`` and
``TestGetUsage``: per-session usage enrichment via a size-0 msearch (terms on
``so_chat.model``, sums on usage fields, value_count on messages), aggregation
floats truncated to int, empty model-bucket keys skipped, positional
``responses[i] <-> sessions[i]`` alignment, per-response ``error`` skipped, and
the single size-0 user-usage aggregation search (terms on ``so_chat.userId``,
cardinality on ``sessionId``, nested ``model_usage`` terms).

The async ES client is mocked with ``unittest.mock.AsyncMock`` (no live ES).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from src.adapters.elasticsearch.assistantstore import ElasticAssistantstore
from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.domain.assistant import AssistantSession, GetSessionsQuery


def _store(es: object) -> ElasticAssistantstore:
    return ElasticAssistantstore(
        ElasticClients(primary=es), ElasticConfig(), requestor_id="u1",
    )


# ----------------------------------------------------------------------
# populate_session_usage
# ----------------------------------------------------------------------


async def test_populate_session_usage_empty_short_circuits() -> None:
    es = AsyncMock()
    await _store(es).populate_session_usage([])
    es.msearch.assert_not_awaited()


async def test_populate_session_usage_success_two_sessions() -> None:
    es = AsyncMock()
    es.msearch.return_value = {"responses": [
        {
            "aggregations": {
                "total_input_tokens": {"value": 1500.0},
                "total_output_tokens": {"value": 3000.0},
                "total_credits": {"value": 5.0},
                "total_messages": {"value": 10.0},
                "model_usage": {"buckets": [
                    {"key": "claude-sonnet-4.5@SOAI",
                     "model_input_tokens": {"value": 1000.0},
                     "model_output_tokens": {"value": 2000.0},
                     "model_credits": {"value": 3.0},
                     "model_messages": {"value": 6.0}},
                    {"key": "gpt-4@OpenAI",
                     "model_input_tokens": {"value": 500.0},
                     "model_output_tokens": {"value": 1000.0},
                     "model_credits": {"value": 2.0},
                     "model_messages": {"value": 4.0}},
                ]},
            },
        },
        {
            "aggregations": {
                "total_input_tokens": {"value": 2500.0},
                "total_output_tokens": {"value": 4500.0},
                "total_credits": {"value": 8.0},
                "total_messages": {"value": 15.0},
                "model_usage": {"buckets": [
                    {"key": "claude-sonnet-4.5@SOAI",
                     "model_input_tokens": {"value": 2500.0},
                     "model_output_tokens": {"value": 4500.0},
                     "model_credits": {"value": 8.0},
                     "model_messages": {"value": 15.0}},
                ]},
            },
        },
    ]}
    sessions = [
        AssistantSession(session_id="session1", title="First Session"),
        AssistantSession(session_id="session2", title="Second Session"),
    ]
    await _store(es).populate_session_usage(sessions)

    assert sessions[0].usage is not None
    assert sessions[0].usage.total_input_tokens == 1500
    assert sessions[0].usage.total_output_tokens == 3000
    assert sessions[0].usage.total_credits == 5
    assert sessions[0].usage.total_messages == 10
    assert sessions[0].usage.model_usage is not None
    assert len(sessions[0].usage.model_usage) == 2
    claude = sessions[0].usage.model_usage["claude-sonnet-4.5@SOAI"]
    assert claude.model_input_tokens == 1000
    assert claude.model_output_tokens == 2000
    assert claude.model_credits == 3
    assert claude.model_messages == 6
    gpt = sessions[0].usage.model_usage["gpt-4@OpenAI"]
    assert gpt.model_input_tokens == 500
    assert gpt.model_messages == 4

    assert sessions[1].usage is not None
    assert sessions[1].usage.total_input_tokens == 2500
    assert sessions[1].usage.total_messages == 15
    assert sessions[1].usage.model_usage is not None
    assert len(sessions[1].usage.model_usage) == 1


async def test_populate_session_usage_skips_error_response() -> None:
    es = AsyncMock()
    es.msearch.return_value = {"responses": [
        {"error": {"type": "index_not_found_exception",
                   "reason": "no such index"}},
        {
            "aggregations": {
                "total_input_tokens": {"value": 2500.0},
                "total_output_tokens": {"value": 4500.0},
                "total_credits": {"value": 8.0},
                "total_messages": {"value": 15.0},
            },
        },
    ]}
    sessions = [
        AssistantSession(session_id="session1", title="First Session"),
        AssistantSession(session_id="session2", title="Second Session"),
    ]
    await _store(es).populate_session_usage(sessions)

    # first session errored -> no usage attached
    assert sessions[0].usage is None
    assert sessions[1].usage is not None
    assert sessions[1].usage.total_input_tokens == 2500
    assert sessions[1].usage.total_credits == 8


async def test_populate_session_usage_zero_values() -> None:
    es = AsyncMock()
    es.msearch.return_value = {"responses": [
        {
            "aggregations": {
                "total_input_tokens": {"value": 0.0},
                "total_output_tokens": {"value": 0.0},
                "total_credits": {"value": 0.0},
                "total_messages": {"value": 0.0},
            },
        },
    ]}
    sessions = [AssistantSession(session_id="session1", title="Empty")]
    await _store(es).populate_session_usage(sessions)

    assert sessions[0].usage is not None
    assert sessions[0].usage.total_input_tokens == 0
    assert sessions[0].usage.total_messages == 0
    # empty bucket list -> model_usage stays None
    assert sessions[0].usage.model_usage is None


async def test_populate_session_usage_query_shape() -> None:
    es = AsyncMock()
    es.msearch.return_value = {"responses": [{"aggregations": {}}]}
    sessions = [AssistantSession(session_id="session1", title="S")]
    await _store(es).populate_session_usage(sessions)

    searches = es.msearch.await_args.kwargs["searches"]
    # header + body per session
    assert len(searches) == 2
    assert searches[0] == {}
    body = searches[1]
    assert body["size"] == 0
    aggs = body["aggs"]
    assert aggs["total_input_tokens"]["sum"]["field"] == (
        "so_chat.message.usage.input_tokens"
    )
    assert aggs["total_messages"]["value_count"]["field"] == "so_chat.sessionId"
    assert aggs["model_usage"]["terms"]["field"] == "so_chat.model"
    assert aggs["model_usage"]["terms"]["size"] == 100
    must = body["query"]["bool"]["must"]
    assert any(c.get("term", {}).get("so_chat.sessionId") == "session1"
               for c in must)
    assert any(c.get("term", {}).get("so_kind") == "chat" for c in must)


async def test_populate_session_usage_targets_cross_cluster_index() -> None:
    es = AsyncMock()
    es.msearch.return_value = {"responses": [{"aggregations": {}}]}
    sessions = [AssistantSession(session_id="session1", title="S")]
    await _store(es).populate_session_usage(sessions)
    assert es.msearch.await_args.kwargs["index"] == "*:so-assistant-chat"


# ----------------------------------------------------------------------
# get_sessions(with_usage=True)
# ----------------------------------------------------------------------


async def test_get_sessions_with_usage_attaches_positionally() -> None:
    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False,
        "hits": {"total": 2, "hits": [
            {"_id": "session1", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session1", "title": "Test",
                               "userId": "u1"}}},
            {"_id": "session2", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session2", "title": "Test",
                               "userId": "u1"}}},
        ]},
    }
    # first msearch -> usage; second msearch -> addMetaFromMessages update_time
    es.msearch.side_effect = [
        {"responses": [
            {"aggregations": {
                "total_input_tokens": {"value": 1000.0},
                "total_output_tokens": {"value": 2000.0},
                "total_credits": {"value": 3.0},
                "total_messages": {"value": 5.0}}},
            {"aggregations": {
                "total_input_tokens": {"value": 4000.0},
                "total_output_tokens": {"value": 5000.0},
                "total_credits": {"value": 6.0},
                "total_messages": {"value": 2.0}}},
        ]},
        {"responses": [{}, {}]},
    ]
    sessions = await _store(es).get_sessions(
        GetSessionsQuery(with_usage=True),
    )
    assert len(sessions) == 2
    assert sessions[0].usage is not None
    assert sessions[0].usage.total_input_tokens == 1000
    assert sessions[0].usage.total_output_tokens == 2000
    assert sessions[0].usage.total_credits == 3
    assert sessions[0].usage.total_messages == 5
    assert sessions[1].usage is not None
    assert sessions[1].usage.total_input_tokens == 4000
    # two msearch calls: usage first, then addMetaFromMessages
    assert es.msearch.await_count == 2


async def test_get_sessions_without_usage_no_usage_msearch() -> None:
    es = AsyncMock()
    es.search.return_value = {
        "took": 1, "timed_out": False,
        "hits": {"total": 1, "hits": [
            {"_id": "session1", "_source": {
                "so_kind": "session",
                "so_session": {"sessionId": "session1", "title": "Test",
                               "userId": "u1"}}},
        ]},
    }
    es.msearch.return_value = {"took": 1, "responses": [{}]}
    sessions = await _store(es).get_sessions(
        GetSessionsQuery(with_usage=False),
    )
    assert sessions[0].usage is None
    # only the addMetaFromMessages msearch runs
    assert es.msearch.await_count == 1


# ----------------------------------------------------------------------
# get_usage
# ----------------------------------------------------------------------


async def test_get_usage_aggregates_per_user() -> None:
    es = AsyncMock()
    es.search.return_value = {"aggregations": {"users": {"buckets": [
        {"key": "user1", "doc_count": 10,
         "total_input_tokens": {"value": 1500.0},
         "total_output_tokens": {"value": 3000.0},
         "total_credits": {"value": 5.0},
         "total_messages": {"value": 10.0},
         "total_sessions": {"value": 3.0},
         "model_usage": {"buckets": [
             {"key": "claude-sonnet-4.5@SOAI",
              "model_input_tokens": {"value": 1000.0},
              "model_output_tokens": {"value": 2000.0},
              "model_credits": {"value": 3.0},
              "model_messages": {"value": 6.0}},
             {"key": "gpt-4@OpenAI",
              "model_input_tokens": {"value": 500.0},
              "model_output_tokens": {"value": 1000.0},
              "model_credits": {"value": 2.0},
              "model_messages": {"value": 4.0}},
         ]}},
        {"key": "user2", "doc_count": 15,
         "total_input_tokens": {"value": 2500.0},
         "total_output_tokens": {"value": 4500.0},
         "total_credits": {"value": 8.0},
         "total_messages": {"value": 15.0},
         "total_sessions": {"value": 5.0},
         "model_usage": {"buckets": [
             {"key": "claude-sonnet-4.5@SOAI",
              "model_input_tokens": {"value": 2500.0},
              "model_output_tokens": {"value": 4500.0},
              "model_credits": {"value": 8.0},
              "model_messages": {"value": 15.0}},
         ]}},
    ]}}}
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2020, 1, 2, tzinfo=UTC)
    usage = await _store(es).get_usage(start, end)

    assert len(usage) == 2
    assert usage[0].user_id == "user1"
    assert usage[0].total_input_tokens == 1500
    assert usage[0].total_output_tokens == 3000
    assert usage[0].total_credits == 5
    assert usage[0].total_messages == 10
    assert usage[0].total_sessions == 3
    assert usage[0].model_usage is not None
    assert len(usage[0].model_usage) == 2
    claude = usage[0].model_usage["claude-sonnet-4.5@SOAI"]
    assert claude.model_input_tokens == 1000
    assert claude.model_output_tokens == 2000
    assert claude.model_credits == 3
    assert claude.model_messages == 6
    gpt = usage[0].model_usage["gpt-4@OpenAI"]
    assert gpt.model_input_tokens == 500
    assert gpt.model_messages == 4

    assert usage[1].user_id == "user2"
    assert usage[1].total_input_tokens == 2500
    assert usage[1].total_sessions == 5
    assert usage[1].model_usage is not None
    assert len(usage[1].model_usage) == 1


async def test_get_usage_query_shape() -> None:
    es = AsyncMock()
    es.search.return_value = {"aggregations": {"users": {"buckets": []}}}
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2020, 1, 2, tzinfo=UTC)
    usage = await _store(es).get_usage(start, end)
    assert usage == []

    body = es.search.await_args.kwargs
    assert es.search.await_args.kwargs["index"] == "*:so-assistant-chat"
    assert body["size"] == 0
    users = body["aggs"]["users"]
    assert users["terms"]["field"] == "so_chat.userId"
    assert users["terms"]["size"] == 10000
    assert users["aggs"]["total_sessions"]["cardinality"]["field"] == (
        "so_chat.sessionId"
    )
    assert users["aggs"]["model_usage"]["terms"]["field"] == "so_chat.model"
    must = body["query"]["bool"]["must"]
    assert any(c.get("term", {}).get("so_kind") == "chat" for c in must)
    ranges = [c for c in must if "range" in c]
    assert ranges
    ts = ranges[0]["range"]["@timestamp"]
    assert ts["gte"] == "2020-01-01T00:00:00Z"
    assert ts["lte"] == "2020-01-02T00:00:00Z"


async def test_get_usage_skips_empty_model_bucket_key() -> None:
    es = AsyncMock()
    es.search.return_value = {"aggregations": {"users": {"buckets": [
        {"key": "user1",
         "total_input_tokens": {"value": 1.0},
         "model_usage": {"buckets": [
             {"key": "",  # empty model key -> skipped
              "model_input_tokens": {"value": 99.0}},
             {"key": "claude",
              "model_input_tokens": {"value": 7.0}},
         ]}},
    ]}}}
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2020, 1, 2, tzinfo=UTC)
    usage = await _store(es).get_usage(start, end)
    assert usage[0].model_usage is not None
    assert list(usage[0].model_usage.keys()) == ["claude"]
    assert usage[0].model_usage["claude"].model_input_tokens == 7
