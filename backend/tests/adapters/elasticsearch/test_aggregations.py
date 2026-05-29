"""Byte-equality tests for the ES aggregation builders (Task 7).

Ported from ``server/modules/elastic/converter_test.go``:
``TestMakeAggregation`` (lines 27-56), ``TestMakeTimeline`` (lines 58-65),
``TestConvertToElasticRequestGroupByCriteria`` (line 106),
``TestConvertToElasticRequestSortByCriteria`` (line 125), and
``TestConvertToElasticRequestGroupBySortByCriteria`` (line 137).

The expected JSON strings are pasted verbatim from the Go ``expectedJson``
literals; byte-equality is asserted at the ``json.dumps(sort_keys=True)``
boundary to match Go's key-sorted ``json.WriteJson`` output.

The heavily-escaped search input is the EXACT byte sequence the Go test passes
to ``criteria.Populate`` (a Go backtick raw string ``q:"\\\\file\\path"``); the
Python query parser reproduces Go's ``mapSearch(...).String()`` byte-for-byte,
including the space after ``q:``.
"""

import json
from datetime import UTC, datetime
from typing import Any

from src.adapters.elasticsearch.query_builder import (
    build_search_request,
    make_aggregation,
    make_timeline,
)
from src.domain.event import EventSearchCriteria
from src.domain.query import Query

# Exact Go input bytes from converter_test.go line 131 (backtick raw string):
#   abc AND def AND q:"\\\\file\\path" | groupby ghi jkl* | groupby mno | sortby ghi jkl^
_GROUPBY_SORTBY_INPUT = (
    r'abc AND def AND q:"\\\\file\\path" '
    r"| groupby ghi jkl* | groupby mno | sortby ghi jkl^"
)
# line 99: groupby only (with a stripped -something option)
_GROUPBY_INPUT = r'abc AND def AND q:"\\\\file\\path" | groupby -something "ghi" jkl*'
# line 113: sortby only
_SORTBY_INPUT = r'abc AND def AND q:"\\\\file\\path" | sortby "ghi" jkl^'


def _sorted(d: dict[str, Any]) -> str:
    # Go's json.WriteJson emits compact, key-sorted JSON; match it for byte-equality.
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def test_make_timeline() -> None:
    assert make_timeline("30m") == {
        "date_histogram": {
            "field": "@timestamp",
            "fixed_interval": "30m",
            "min_doc_count": 1,
        }
    }


def test_make_aggregation_star_and_nesting() -> None:
    agg, name = make_aggregation({}, "groupby_0", ["one*", "two", "three*"], 10, ascending=False)
    assert name == "groupby_0|one"
    assert agg["terms"]["field"] == "one"
    assert agg["terms"]["missing"] == "__missing__"
    assert agg["terms"]["size"] == 10
    assert agg["terms"]["order"] == {"_count": "desc"}

    inner = agg["aggs"]["groupby_0|one|two"]
    assert "missing" not in inner["terms"]
    deepest = inner["aggs"]["groupby_0|one|two|three"]
    assert deepest["terms"]["missing"] == "__missing__"
    assert "aggs" not in deepest


def test_make_aggregation_ascending_order() -> None:
    agg, _ = make_aggregation({}, "groupby_0", ["one"], 10, ascending=True)
    assert agg["terms"]["order"] == {"_count": "asc"}


def test_make_aggregation_does_not_mutate_caller_keys() -> None:
    keys = ["one*", "two"]
    make_aggregation({}, "groupby_0", keys, 10, ascending=False)
    assert keys == ["one*", "two"]  # caller's list untouched


def _criteria(query: str) -> EventSearchCriteria:
    c = EventSearchCriteria()
    c.metric_limit = 10
    c.event_limit = 25
    c.begin_time = datetime(2020, 1, 2, 12, 13, 14, tzinfo=UTC)
    c.end_time = datetime(2020, 1, 2, 13, 13, 14, tzinfo=UTC)
    c.parsed_query = Query()
    assert c.parsed_query.parse(query) is None
    return c


def test_build_search_groupby_matches_go() -> None:
    # converter_test.go line 106
    expected = (
        '{"aggs":{"bottom":{"terms":{"field":"ghi","order":{"_count":"asc"},"size":10}},'
        '"groupby_0|ghi":{"aggs":{"groupby_0|ghi|jkl":{"terms":{"field":"jkl",'
        '"missing":"__missing__","order":{"_count":"desc"},"size":10}}},'
        '"terms":{"field":"ghi","order":{"_count":"desc"},"size":10}},'
        '"timeline":{"date_histogram":{"field":"@timestamp","fixed_interval":"1m",'
        '"min_doc_count":1}}},"query":{"bool":{"filter":[],"must":[{"query_string":'
        '{"analyze_wildcard":true,"default_field":"*",'
        '"query":"abc AND def AND q: \\"\\\\\\\\\\\\\\\\file\\\\\\\\path\\""}},'
        '{"range":{"@timestamp":{"format":"strict_date_optional_time",'
        '"gte":"2020-01-02T12:13:14Z","lte":"2020-01-02T13:13:14Z"}}}],'
        '"must_not":[],"should":[]}},"size":25}'
    )
    assert _sorted(build_search_request({}, 25, _criteria(_GROUPBY_INPUT))) == expected


def test_build_search_sortby_matches_go() -> None:
    # converter_test.go line 125
    expected = (
        '{"aggs":{"timeline":{"date_histogram":{"field":"@timestamp",'
        '"fixed_interval":"1m","min_doc_count":1}}},"query":{"bool":{"filter":[],'
        '"must":[{"query_string":{"analyze_wildcard":true,"default_field":"*",'
        '"query":"abc AND def AND q: \\"\\\\\\\\\\\\\\\\file\\\\\\\\path\\""}},'
        '{"range":{"@timestamp":{"format":"strict_date_optional_time",'
        '"gte":"2020-01-02T12:13:14Z","lte":"2020-01-02T13:13:14Z"}}}],'
        '"must_not":[],"should":[]}},"size":25,'
        '"sort":[{"ghi":{"missing":"_last","order":"desc","unmapped_type":"date"}},'
        '{"jkl":{"missing":"_last","order":"asc","unmapped_type":"date"}}]}'
    )
    assert _sorted(build_search_request({}, 25, _criteria(_SORTBY_INPUT))) == expected


def test_build_search_groupby_sortby_matches_go() -> None:
    # converter_test.go line 137
    expected = (
        '{"aggs":{"bottom":{"terms":{"field":"ghi","order":{"_count":"asc"},"size":10}},'
        '"groupby_0|ghi":{"aggs":{"groupby_0|ghi|jkl":{"terms":{"field":"jkl",'
        '"missing":"__missing__","order":{"_count":"desc"},"size":10}}},'
        '"terms":{"field":"ghi","order":{"_count":"desc"},"size":10}},'
        '"groupby_1|mno":{"terms":{"field":"mno","order":{"_count":"desc"},"size":10}},'
        '"timeline":{"date_histogram":{"field":"@timestamp","fixed_interval":"1m",'
        '"min_doc_count":1}}},"query":{"bool":{"filter":[],"must":[{"query_string":'
        '{"analyze_wildcard":true,"default_field":"*",'
        '"query":"abc AND def AND q: \\"\\\\\\\\\\\\\\\\file\\\\\\\\path\\""}},'
        '{"range":{"@timestamp":{"format":"strict_date_optional_time",'
        '"gte":"2020-01-02T12:13:14Z","lte":"2020-01-02T13:13:14Z"}}}],'
        '"must_not":[],"should":[]}},"size":25,'
        '"sort":[{"ghi":{"missing":"_last","order":"desc","unmapped_type":"date"}},'
        '{"jkl":{"missing":"_last","order":"asc","unmapped_type":"date"}}]}'
    )
    assert _sorted(build_search_request({}, 25, _criteria(_GROUPBY_SORTBY_INPUT))) == expected
