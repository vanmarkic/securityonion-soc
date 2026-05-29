"""Tests for ElasticEventstore.get_active_queries + cancel_query.

Ports ``elasticqueries.go`` ``getActiveQueries`` / ``cancelQuery`` (tasks API).
The Python port takes no ctx and performs no CheckAuthorized (auth is at the
route layer). The Go latent bug (it lists tasks on the primary client and
checks the wrong error variable) is FIXED here: we list on each loop client and
cancel on the originating client.
"""

import pytest

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.eventstore import ElasticEventstore

_TASKS = {
    "nodes": {
        "n1": {
            "tasks": {
                "n1:1": {
                    "cancellable": True,
                    "action": "indices:data/read/search",
                    "type": "transport",
                    "start_time_in_millis": 1700000000000,
                    "running_time_in_nanos": 5_000_000,
                    "parent_task_id": "",
                },
                "n1:2": {
                    "cancellable": False,
                    "action": "cluster:monitor/tasks/lists",
                    "type": "transport",
                    "start_time_in_millis": 1700000000000,
                    "running_time_in_nanos": 1_000_000,
                    "parent_task_id": "",
                },
            },
        },
    },
}


def _make_es(tasks_body):
    """Build a mock ES client whose ``tasks.list`` returns ``tasks_body``.

    A plain AsyncMock auto-creates ``tasks.list``/``tasks.cancel`` as async
    children, which is exactly what the adapter awaits.
    """
    from unittest.mock import AsyncMock

    es = AsyncMock()
    es.tasks.list.return_value = tasks_body
    return es


async def test_get_active_queries_uses_tasks_list():
    es = _make_es(_TASKS)
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig())
    tasks = await store.get_active_queries(True)
    assert len(tasks) == 1
    es.tasks.list.assert_awaited_once()


async def test_get_active_queries_no_filter_keeps_all():
    es = _make_es(_TASKS)
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig())
    tasks = await store.get_active_queries(False)
    assert len(tasks) == 2


async def test_get_active_queries_lists_each_client_not_just_primary():
    es1 = _make_es(_TASKS)
    es2 = _make_es(_TASKS)
    store = ElasticEventstore(
        ElasticClients(primary=es1, remotes=[es2]), ElasticConfig(),
    )
    tasks = await store.get_active_queries(True)
    # Bug-fixed: each loop client is listed (Go listed primary every time).
    es1.tasks.list.assert_awaited_once()
    es2.tasks.list.assert_awaited_once()
    assert len(tasks) == 2


async def test_cancel_query_finds_task_and_cancels_on_its_client():
    es = _make_es(_TASKS)
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig())
    await store.cancel_query("n1:1")
    es.tasks.cancel.assert_awaited_once_with(task_id="n1:1")


async def test_cancel_query_cancels_on_owning_remote_client():
    es1 = _make_es({"nodes": {}})
    es2 = _make_es(_TASKS)
    store = ElasticEventstore(
        ElasticClients(primary=es1, remotes=[es2]), ElasticConfig(),
    )
    await store.cancel_query("n1:1")
    es1.tasks.cancel.assert_not_awaited()
    es2.tasks.cancel.assert_awaited_once_with(task_id="n1:1")


async def test_cancel_query_not_found_raises():
    es = _make_es({"nodes": {}})
    store = ElasticEventstore(ElasticClients(primary=es), ElasticConfig())
    with pytest.raises(Exception, match="query not found"):
        await store.cancel_query("missing")
