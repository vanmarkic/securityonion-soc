"""Tests for converter response mapping (Task 8).

Ports converter_test.go: TestConvertFromElasticResultsSuccess/Failure/TimedOut/Invalid,
TestConvertFromElasticUpdateResultsSuccess, TestConvertFromElasticIndexResults,
TestConvertFromElasticMSearchResults, plus flatten/parse_aggregation coverage.
"""

import json
from pathlib import Path

from src.adapters.elasticsearch.converter import (
    flatten,
    parse_index_results,
    parse_msearch_results,
    parse_scroll_results,
    parse_search_results,
    parse_update_results,
)
from src.domain.event import (
    EventMSearchResults,
    EventSearchResults,
    EventUpdateResults,
)

FIX = Path(__file__).parent / "fixtures"


def test_flatten_dotted_keys():
    assert flatten({}, {"a": {"b": 1}}) == {"a.b": 1}


def test_flatten_leaves_scalars_and_lists():
    assert flatten({}, {"a": 1, "b": ["x", "y"], "c": {"d": {"e": 2}}}) == {
        "a": 1,
        "b": ["x", "y"],
        "c.d.e": 2,
    }


def test_parse_search_results_success():
    body = json.loads((FIX / "converter_response.json").read_text())
    res = EventSearchResults()
    err = parse_search_results({}, body, res)
    assert err is None
    assert res.elapsed_ms == 9534
    assert res.total_events == 23689430  # hits.total is a bare number here
    assert len(res.events) == 25
    # timestamp normalization: ms-precision UTC literal Z (matches Go format)
    assert res.events[0].timestamp == "2020-04-24T03:00:55.300Z"
    assert res.events[1].timestamp == "2020-04-24T03:00:55.038Z"  # alternate field
    assert res.events[0].source == "so16:logstash-bro-2020.04.24"
    # 4 nested groupby metrics present (Go asserts these specific keys NotNil)
    assert "groupby_0|source_ip" in res.metrics
    assert "groupby_0|source_ip|destination_ip" in res.metrics
    assert "groupby_0|source_ip|destination_ip|protocol" in res.metrics
    assert "groupby_0|source_ip|destination_ip|protocol|destination_port" in res.metrics


def test_parse_search_results_timed_out():
    res = EventSearchResults()
    err = parse_search_results({}, {"took": 123, "timed_out": True, "hits": {}}, res)
    assert err == "Timeout while fetching results from Elasticsearch"
    assert res.elapsed_ms == 123  # ElapsedMs set even on timeout


def test_parse_search_results_invalid():
    res = EventSearchResults()
    err = parse_search_results({}, {}, res)
    assert err == "Elasticsearch response is not a valid JSON search result"


def test_parse_search_results_shard_failure_keeps_events():
    body = json.loads((FIX / "converter_response_failure.json").read_text())
    res = EventSearchResults()
    err = parse_search_results({}, body, res)
    assert err == "ERROR_QUERY_FAILED_ELASTICSEARCH"
    # events/metrics still populated despite the shard failure
    assert res.elapsed_ms == 9534
    assert res.total_events == 23689430
    assert len(res.events) == 25
    assert res.events[0].timestamp == "2020-04-24T03:00:55.300Z"
    assert "groupby_0|source_ip" in res.metrics


def test_parse_search_results_shard_failure_no_events():
    # mirror TestConvertFromElasticResults_Failure: failed shards, empty hits
    body = {
        "took": 11,
        "timed_out": False,
        "_shards": {"total": 28, "successful": 16, "skipped": 0, "failed": 12},
        "hits": {"hits": [], "total": {"value": 0}},
    }
    res = EventSearchResults()
    err = parse_search_results({}, body, res)
    assert err == "ERROR_QUERY_FAILED_ELASTICSEARCH"
    assert res.total_events == 0  # hits.total as object -> value


def test_parse_scroll_results_success():
    body = json.loads((FIX / "converter_response.json").read_text())
    res = EventSearchResults()
    err = parse_scroll_results({}, body, res)
    assert err is None
    assert res.total_events == 23689430
    assert len(res.events) == 25


def test_parse_update_results():
    res = EventUpdateResults()
    err = parse_update_results(
        {"took": 202, "timed_out": False, "updated": 3, "noops": 2}, res
    )
    assert err is None
    assert res.elapsed_ms == 202
    assert res.updated_count == 3
    assert res.unchanged_count == 2


def test_parse_update_results_invalid():
    res = EventUpdateResults()
    err = parse_update_results({"took": 1}, res)
    assert err == "Elasticsearch response is not a valid JSON updated result"


def test_parse_update_results_timed_out():
    res = EventUpdateResults()
    err = parse_update_results(
        {"took": 5, "timed_out": True, "updated": 0, "noops": 0}, res
    )
    assert err == "Timeout while updating documents in Elasticsearch"
    assert res.elapsed_ms == 5


def test_parse_index_results_success_states():
    r = parse_index_results({"_id": "abc", "result": "created"})
    assert r.document_id == "abc"
    assert r.success is True
    assert parse_index_results({"_id": "x", "result": "updated"}).success is True
    assert parse_index_results({"_id": "x", "result": "deleted"}).success is False


def test_parse_msearch_results():
    # mirror TestConvertFromElasticMSearchResults: wrap the success fixture as one response
    inner = json.loads((FIX / "converter_response.json").read_text())
    body = {"took": 10, "responses": [inner]}
    res = EventMSearchResults()
    err = parse_msearch_results({}, body, res)
    assert err is None
    assert res.elapsed_ms == 10
    assert len(res.responses) == 1
    response = res.responses[0]
    assert response.elapsed_ms == 9534
    assert response.total_events == 23689430
    assert len(response.events) == 25
    assert response.events[0].timestamp == "2020-04-24T03:00:55.300Z"


def test_parse_msearch_results_error():
    res = EventMSearchResults()
    body = {"took": 1, "responses": [{"error": {"reason": "boom"}}]}
    err = parse_msearch_results({}, body, res)
    assert err == "boom"
