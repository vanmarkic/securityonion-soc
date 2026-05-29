"""Byte-equality tests for the ES request builders (Task 6).

Ported from ``server/modules/elastic/converter_test.go``:
``TestCalcTimelineInterval`` (lines 67-83), ``TestConvertToElasticRequestEmptyCriteria``
(line 92), ``TestConvertToElasticScrollRequestEmpty`` (line 616),
``TestConvertToElasticRequestProgrammaticSortBy`` (line 151), and
``TestConvertToElasticUpdateRequest`` (line 221).

Byte-equality is asserted at the ``json.dumps(sort_keys=True)`` boundary to match
Go's key-sorted ``json.WriteJson`` output.
"""

import json
from datetime import UTC, datetime
from typing import Any

from src.adapters.elasticsearch.query_builder import (
    build_scroll_request,
    build_search_request,
    build_update_request,
    calc_timeline_interval,
)
from src.domain.event import EventSearchCriteria, EventUpdateCriteria, SortCriteria
from src.domain.query import Query


def _sorted(d: dict[str, Any]) -> str:
    # Go's json.WriteJson emits compact, key-sorted JSON (no spaces). Match it
    # with sort_keys + compact separators for true byte-equality.
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def test_calc_timeline_interval_ladder() -> None:
    # 8h / 25 intervals -> 1152s -> "15m" (matches Go 05:00->13:00)
    eight_h = (
        datetime(2021, 1, 2, 5, tzinfo=UTC),
        datetime(2021, 1, 2, 13, tzinfo=UTC),
    )
    assert calc_timeline_interval(25, *eight_h) == "15m"

    one_s = (
        datetime(2021, 1, 2, 13, 0, 0, tzinfo=UTC),
        datetime(2021, 1, 2, 13, 0, 1, tzinfo=UTC),
    )
    assert calc_timeline_interval(25, *one_s) == "1s"

    huge = (
        datetime(1990, 1, 2, 5, tzinfo=UTC),
        datetime(2021, 1, 2, 13, tzinfo=UTC),
    )
    assert calc_timeline_interval(25, *huge) == "30d"


def test_build_search_empty_matches_go() -> None:
    c = EventSearchCriteria()
    c.metric_limit = 0
    c.event_limit = 25
    c.parsed_query = Query()
    c.parsed_query.parse("*")
    expected = (
        '{"query":{"bool":{"filter":[],"must":[{"query_string":'
        '{"analyze_wildcard":true,"default_field":"*","query":"*"}}],'
        '"must_not":[],"should":[]}},"size":25}'
    )
    assert _sorted(build_search_request({}, 25, c)) == expected


def test_build_scroll_empty_matches_go() -> None:
    c = EventSearchCriteria()
    c.parsed_query = Query()
    c.parsed_query.parse("*")
    expected = (
        '{"query":{"bool":{"filter":[],"must":[{"query_string":'
        '{"analyze_wildcard":true,"default_field":"*","query":"*"}}],'
        '"must_not":[],"should":[]}},"size":10000}'
    )
    assert _sorted(build_scroll_request({}, c, 10000)) == expected


def test_build_search_programmatic_sortfields_is_map() -> None:
    c = EventSearchCriteria()
    c.metric_limit = 0
    c.event_limit = 25
    c.parsed_query = Query()
    c.parsed_query.parse("*")
    c.sort_fields = [SortCriteria("name", "asc")]
    expected = (
        '{"query":{"bool":{"filter":[],"must":[{"query_string":'
        '{"analyze_wildcard":true,"default_field":"*","query":"*"}}],'
        '"must_not":[],"should":[]}},"size":25,"sort":{"name":"asc"}}'
    )
    assert _sorted(build_search_request({}, 25, c)) == expected


def test_build_update_request_two_scripts_with_range() -> None:
    c = EventUpdateCriteria()
    c.parsed_query = Query()
    c.parsed_query.parse("event.dataset:alerts")
    c.begin_time = datetime(2020, 9, 24, 10, 11, 12, tzinfo=UTC)
    c.end_time = datetime(2020, 9, 24, 12, 14, 15, tzinfo=UTC)
    c.update_scripts = [
        "ctx._source.event.acknowledged=true",
        "ctx._source.event.escalated=true",
    ]
    body = build_update_request({}, c)
    assert (
        body["script"]["source"]
        == "ctx._source.event.acknowledged=true; ctx._source.event.escalated=true"
    )
    assert body["script"]["lang"] == "painless"
    assert "range" in body["query"]["bool"]["must"][1]
