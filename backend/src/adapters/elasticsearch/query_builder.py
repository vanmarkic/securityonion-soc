"""Elasticsearch DSL query builder (pure layer).

Port of the request-building functions in
``server/modules/elastic/converter.go``: ``makeQuery``, ``formatSearch``,
``mapSearch``, ``stripSegmentOptions``. No I/O — these synchronous helpers
translate parsed SOC :class:`~src.domain.query.Query` objects into the
Elasticsearch query DSL ``dict`` shapes that the Go module emitted via
``json.WriteJson``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.adapters.elasticsearch.field_caps import FieldDefinition, map_elastic_field
from src.domain.event import EventSearchCriteria, EventUpdateCriteria
from src.domain.query import SEGMENT_KIND_SEARCH, SEGMENT_KIND_SORT_BY, BaseSegment, Query


def format_search(value: str) -> str:
    """Trim spaces and default an empty search to ``*`` (Go ``formatSearch``)."""
    trimmed = value.strip(" ")  # Go strings.Trim(input, " ") — space only
    return trimmed if trimmed else "*"


def strip_segment_options(keys: list[str]) -> list[str]:
    """Drop ``-``-prefixed option keys (Go ``stripSegmentOptions``)."""
    return [k for k in keys if not k.startswith("-")]


def _rfc3339(dt: datetime) -> str:
    """Format like Go ``time.Format(time.RFC3339)`` (offset preserved, no micros)."""
    s = dt.strftime("%Y-%m-%dT%H:%M:%S")
    off = dt.utcoffset()
    if off is None or off.total_seconds() == 0:
        return s + "Z"
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{s}{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def map_search(defs: dict[str, FieldDefinition], search_segment: BaseSegment) -> BaseSegment:
    """Remap bare ``field:`` terms to their aggregatable ``.keyword`` twin.

    Mirrors Go ``mapSearch``: for each term whose raw value ends with ``:`` and
    is neither grouped nor quoted, the field name is remapped via
    ``map_elastic_field`` and the term rewritten in place.
    """
    delim = ":"
    for term in search_segment.terms:
        if term.raw.endswith(delim) and not term.grouped and not term.quoted:
            field = term.raw.strip(delim)  # Go strings.Trim(term.Raw, ":")
            new_field = map_elastic_field(defs, field)
            if new_field != field:
                term.raw = new_field + delim
    return search_segment


def make_query(
    defs: dict[str, FieldDefinition],
    parsed: Query,
    begin: datetime | None,
    end: datetime | None,
) -> dict[str, Any]:
    """Build the ``bool`` query DSL for a parsed query (Go ``makeQuery``).

    The four boolean clause arrays (``must``/``filter``/``should``/``must_not``)
    are always present, matching Go's ``make([]interface{}, 0)`` semantics. A
    ``@timestamp`` range clause is appended to ``must`` only when ``end`` is a
    non-zero time (Go ``!endTime.IsZero()``).
    """
    search_str = ""
    segment = parsed.named_segment(SEGMENT_KIND_SEARCH)
    if segment is not None:
        search_str = str(map_search(defs, segment))

    must: list[dict[str, Any]] = [
        {
            "query_string": {
                "query": format_search(search_str),
                "analyze_wildcard": True,
                "default_field": "*",
            }
        }
    ]

    if end is not None:  # Go: range clause only when EndTime is non-zero
        must.append(
            {
                "range": {
                    "@timestamp": {
                        "gte": _rfc3339(begin) if begin is not None else _rfc3339(end),
                        "lte": _rfc3339(end),
                        "format": "strict_date_optional_time",
                    }
                }
            }
        )

    return {
        "bool": {
            "must": must,
            "filter": [],
            "should": [],
            "must_not": [],
        }
    }


# Each tuple is ``(threshold_seconds, label)``: the first rung whose threshold is
# >= the per-interval second count wins. A direct port of the cascading
# ``if intervalSeconds <= N`` ladder in Go ``calcTimelineInterval``.
_INTERVAL_LADDER: list[tuple[int, str]] = [
    (3, "1s"),
    (7, "5s"),
    (13, "10s"),
    (23, "15s"),
    (45, "30s"),
    (180, "1m"),
    (420, "5m"),
    (780, "10m"),
    (1380, "15m"),
    (2700, "30m"),
    (5400, "1h"),
    (25200, "5h"),
    (54000, "10h"),
    (259200, "1d"),
    (604800, "5d"),
    (1296000, "10d"),
]


def calc_timeline_interval(intervals: int, begin: datetime, end: datetime) -> str:
    """Pick the histogram interval nearest ``(end - begin) / intervals`` seconds.

    Direct port of Go ``calcTimelineInterval``; returns ``"30d"`` when the
    per-interval span exceeds the largest ladder rung.
    """
    interval_seconds = (end - begin).total_seconds() / intervals
    for threshold, label in _INTERVAL_LADDER:
        if interval_seconds <= threshold:
            return label
    return "30d"


def _sort_from_criteria(
    parsed: Query, sort_fields: list[Any],
) -> list[dict[str, Any]] | dict[str, str] | None:
    """Build the ``sort`` clause (Go ``convertToElasticRequest`` sort logic).

    A ``sortby`` segment in the parsed query takes precedence and produces an
    ordered **array** of ``{field: {order, missing, unmapped_type}}`` maps
    (``^`` suffix flips ``desc`` -> ``asc``). Otherwise the programmatic
    ``sort_fields`` produce a flat ``{field: order}`` **map**. ``None`` means no
    sort clause (Go omits the key when empty).
    """
    segment = parsed.named_segment(SEGMENT_KIND_SORT_BY)
    if segment is not None:
        fields = segment.raw_fields()
        if fields:
            sorting: list[dict[str, Any]] = []
            for field in fields:
                order = "desc"
                name = field
                if field.endswith("^"):
                    order = "asc"
                    name = field[:-1]
                sorting.append(
                    {name: {"order": order, "missing": "_last", "unmapped_type": "date"}}
                )
            if sorting:
                return sorting
        return None
    sort_map = {sc.field: sc.order for sc in sort_fields}
    return sort_map if sort_map else None


def _build_aggregations(
    defs: dict[str, FieldDefinition], criteria: EventSearchCriteria,
) -> dict[str, Any]:
    """Placeholder replaced in Task 7 (terms/timeline/bottom aggregations)."""
    return {}


def build_search_request(
    defs: dict[str, FieldDefinition], intervals: int, criteria: EventSearchCriteria,
) -> dict[str, Any]:
    """Build a ``_search`` request body (Go ``convertToElasticRequest``).

    ``size`` comes from ``criteria.event_limit``; ``search_after`` is added only
    when present; aggregations are added when ``metric_limit > 0`` (Task 7); the
    sort clause is added per :func:`_sort_from_criteria`.
    """
    body: dict[str, Any] = {
        "size": criteria.event_limit,
        "query": make_query(
            defs, criteria.parsed_query, criteria.begin_time, criteria.end_time,
        ),
    }
    if criteria.search_after:
        body["search_after"] = criteria.search_after
    if criteria.metric_limit > 0:
        aggs = _build_aggregations(defs, criteria)
        if aggs:
            body["aggs"] = aggs
    sort = _sort_from_criteria(criteria.parsed_query, criteria.sort_fields)
    if sort is not None:
        body["sort"] = sort
    return body


def build_scroll_request(
    defs: dict[str, FieldDefinition], criteria: EventSearchCriteria, max_scroll_size: int,
) -> dict[str, Any]:
    """Build a scroll request body (Go ``convertToElasticScrollRequest``)."""
    body: dict[str, Any] = {
        "size": max_scroll_size,
        "query": make_query(
            defs, criteria.parsed_query, criteria.begin_time, criteria.end_time,
        ),
    }
    sort = _sort_from_criteria(criteria.parsed_query, criteria.sort_fields)
    if sort is not None:
        body["sort"] = sort
    return body


def build_msearch_request(
    defs: dict[str, FieldDefinition], criteria: EventSearchCriteria,
) -> dict[str, Any]:
    """Build an msearch sub-request body (Go ``convertToElasticMSearchRequest``).

    Always uses zero times, so no ``@timestamp`` range clause is emitted.
    """
    return {"query": make_query(defs, criteria.parsed_query, None, None)}


def build_update_request(
    defs: dict[str, FieldDefinition], criteria: EventUpdateCriteria,
) -> dict[str, Any]:
    """Build an update-by-query request body (Go ``convertToElasticUpdateRequest``).

    Joins the update scripts with ``"; "`` (painless), attaching ``params`` only
    when present.
    """
    script: dict[str, Any] = {
        "source": "; ".join(criteria.update_scripts),
        "lang": "painless",
    }
    if criteria.params:
        script["params"] = criteria.params
    return {
        "query": make_query(
            defs, criteria.parsed_query, criteria.begin_time, criteria.end_time,
        ),
        "script": script,
    }
