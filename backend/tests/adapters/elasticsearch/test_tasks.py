"""Tests for the pure tasks-list parser (parse_query_tasks).

Ports ``server/modules/elastic/elasticqueries.go``
``convertFromElasticQueryTaskResults`` (+ ``elasticqueries_test.go``
``TestConvertFromElasticQueryTaskResults``). The originating client is attached
to each returned ``QueryTask`` so ``cancel_query`` can cancel on the owning
client (multi-cluster correctness).
"""

from src.adapters.elasticsearch.tasks import parse_query_tasks

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


def test_parse_query_tasks_filter_excludes_noncancelable_and_listself():
    tasks = parse_query_tasks(_TASKS, client="C", grid_id="", filter_internal=True)
    assert [t.task_id for t in tasks] == ["n1:1"]
    assert tasks[0].cancelable is True
    assert tasks[0].elapsed_ms == 5  # nanos / 1e6


def test_parse_query_tasks_no_filter_keeps_all():
    tasks = parse_query_tasks(_TASKS, client="C", grid_id="", filter_internal=False)
    assert len(tasks) == 2


def test_parse_query_tasks_details_and_grid_id():
    tasks = parse_query_tasks(_TASKS, client="C", grid_id="myGrid", filter_internal=True)
    assert tasks[0].details == "transport (indices:data/read/search)"
    assert tasks[0].grid_id == "myGrid"


def test_parse_query_tasks_attaches_originating_client():
    tasks = parse_query_tasks(_TASKS, client="C", grid_id="", filter_internal=True)
    assert tasks[0]._client == "C"


def test_parse_query_tasks_excludes_persistent_and_child():
    body = {
        "nodes": {
            "n1": {
                "tasks": {
                    "persistent_task": {
                        "cancellable": True,
                        "action": "indices:data/read/search",
                        "type": "persistent",
                        "start_time_in_millis": 1700000000000,
                        "running_time_in_nanos": 5_000_000,
                        "parent_task_id": "",
                    },
                    "child_task": {
                        "cancellable": True,
                        "action": "indices:data/read/search",
                        "type": "transport",
                        "start_time_in_millis": 1700000000000,
                        "running_time_in_nanos": 5_000_000,
                        "parent_task_id": "n1:99",
                    },
                },
            },
        },
    }
    tasks = parse_query_tasks(body, client="C", grid_id="", filter_internal=True)
    assert tasks == []
