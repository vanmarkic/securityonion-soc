"""Pure parser for the Elasticsearch tasks-list response.

Ports ``server/modules/elastic/elasticqueries.go``
``convertFromElasticQueryTaskResults`` (+ the ``ElasticTask`` /
``ElasticNodeTasks`` / ``ElasticTaskResults`` response models). Translates a
raw ``_tasks`` list response into a list of domain ``QueryTask`` objects.

The originating ES client is attached to each ``QueryTask`` as the ``_client``
attribute so the I/O layer (``ElasticEventstore.cancel_query``) can cancel on
the client that owns the task (multi-cluster correctness — see the bug-fix note
in ``eventstore.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.ports.events import QueryTask

# Filter-excluded list-tasks self-action (Go: "cluster:monitor/tasks/lists").
_LIST_TASKS_ACTION = "cluster:monitor/tasks/lists"
_NANOS_PER_MS = 1_000_000
_ZERO_TIMESTAMP = "0001-01-01T00:00:00Z"


def _format_start_time(start_time_in_millis: Any) -> str:
    """Format ``start_time_in_millis`` as ms-precision UTC literal-Z.

    Go stores ``StartTime`` as ``time.Unix(0, millis*1e6)``; the Python domain
    ``QueryTask.start_time`` is a string, so we render the same instant in the
    ms-precision literal-Z layout used across the adapter
    (``f"{dt:%Y-%m-%dT%H:%M:%S}.{ms:03d}Z"``). Non-integer values fall back to
    the zero timestamp rather than raising (the port is lenient where Go was
    strict on JSON unmarshal).
    """
    if not isinstance(start_time_in_millis, (int, float)) or isinstance(
        start_time_in_millis, bool,
    ):
        return _ZERO_TIMESTAMP
    dt = datetime.fromtimestamp(start_time_in_millis / 1000.0, tz=UTC)
    return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{dt.microsecond // 1000:03d}Z"


def _include_task(task: dict[str, Any]) -> bool:
    """Mirror Go's filter: drop permanent, child, non-cancelable, and self."""
    if not task.get("cancellable", False):
        return False
    if task.get("type") == "persistent":
        return False
    if task.get("parent_task_id"):
        return False
    return task.get("action") != _LIST_TASKS_ACTION


def parse_query_tasks(
    body: dict[str, Any],
    *,
    client: Any,
    grid_id: str,
    filter_internal: bool,
) -> list[QueryTask]:
    """Convert a raw ``_tasks`` list response into domain ``QueryTask`` objects.

    When ``filter_internal`` is True, permanent/child/non-cancelable tasks and
    the list-tasks self-query are excluded (Go's ``filter`` behavior). The
    originating ``client`` is attached as ``task._client``.
    """
    tasks: list[QueryTask] = []
    nodes = body.get("nodes", {})
    for node in nodes.values():
        for task_id, task in node.get("tasks", {}).items():
            if filter_internal and not _include_task(task):
                continue
            action = task.get("action", "")
            type_ = task.get("type", "")
            elapsed_ms = int(task.get("running_time_in_nanos", 0)) // _NANOS_PER_MS
            query_task = QueryTask(
                grid_id=grid_id,
                task_id=task_id,
                details=f"{type_} ({action})",
                start_time=_format_start_time(task.get("start_time_in_millis")),
                elapsed_ms=elapsed_ms,
                cancelable=bool(task.get("cancellable", False)),
            )
            # Track the owning client for cancel_query (bug-fixed multi-cluster).
            query_task._client = client  # type: ignore[attr-defined]
            tasks.append(query_task)
    return tasks
