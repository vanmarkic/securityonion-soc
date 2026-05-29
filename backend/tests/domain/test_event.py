"""Tests for Event domain models — ported from Go model/event_test.go."""

import time as time_mod

from src.domain.event import (
    new_event_search_criteria,
    new_event_search_results,
    new_event_update_criteria,
    new_event_update_results,
)


class TestNewEventSearchCriteria:
    def test_has_create_time(self):
        criteria = new_event_search_criteria()
        assert criteria.create_time is not None


class TestNewEventUpdateCriteria:
    def test_has_create_time(self):
        criteria = new_event_update_criteria()
        assert criteria.create_time is not None


class TestPopulate:
    def test_query_trim(self):
        good_time = "2006-05-07T14:15:59+01:00 - 2006-05-07T14:16:59+01:00"
        zone = "America/New_York"
        criteria = new_event_search_criteria()
        err = criteria.populate(" foo ", good_time, "%Y-%m-%dT%H:%M:%S%z", zone, "10", "100")
        assert err is None
        assert criteria.raw_query == "foo"

    def test_bad_start_and_end_times(self):
        bad_time = "2006-05-07"
        _good_time = "2006-05-07T14:15:59+01:00"
        zone = "America/New_York"
        criteria = new_event_search_criteria()
        err = criteria.populate("foo", bad_time + " - " + bad_time, "%Y-%m-%dT%H:%M:%S%z", zone, "10", "100")
        assert err is not None, "expected error from bad start time and end time input"

    def test_bad_start_time(self):
        bad_time = "2006-05-07"
        good_time = "2006-05-07T14:15:59+01:00"
        zone = "America/New_York"
        criteria = new_event_search_criteria()
        err = criteria.populate("foo", bad_time + " - " + good_time, "%Y-%m-%dT%H:%M:%S%z", zone, "10", "100")
        assert err is not None, "expected error from bad start time input"

    def test_bad_end_time(self):
        bad_time = "2006-05-07"
        good_time = "2006-05-07T14:15:59+01:00"
        zone = "America/New_York"
        criteria = new_event_search_criteria()
        err = criteria.populate("foo", good_time + " - " + bad_time, "%Y-%m-%dT%H:%M:%S%z", zone, "10", "100")
        assert err is not None, "expected error from bad end time input"

    def test_good_times(self):
        good_time = "2006-05-07T14:15:59+01:00"
        zone = "America/New_York"
        criteria = new_event_search_criteria()
        err = criteria.populate("foo", good_time + " - " + good_time, "%Y-%m-%dT%H:%M:%S%z", zone, "30", "100")
        assert err is None, "expected no error from good time input"


class TestLimits:
    def test_event_and_metric_limits(self):
        good_time = "2006-05-07T14:15:59+01:00"
        criteria = new_event_search_criteria()
        _ = criteria.populate("foo", good_time + " - " + good_time, "%Y-%m-%dT%H:%M:%S%z", "PST", "30", "100")
        assert criteria.event_limit == 100
        assert criteria.metric_limit == 30


class TestEventSearchResults:
    def test_complete_time_after_create_time(self):
        results = new_event_search_results()
        time_mod.sleep(0.001)  # ensure time passes
        results.complete()
        assert results.complete_time > results.create_time
        assert len(results.errors) == 0


class TestEventUpdateResults:
    def test_complete_time_after_create_time(self):
        results = new_event_update_results()
        time_mod.sleep(0.001)  # ensure time passes
        results.complete()
        assert results.complete_time > results.create_time
        assert len(results.errors) == 0
