"""Tests for Job domain model — ported from Go model/job_test.go."""

from datetime import datetime, timedelta, timezone

from src.domain.job import (
    DEFAULT_JOB_KIND,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_DELETED,
    JOB_STATUS_INCOMPLETE,
    JOB_STATUS_PENDING,
    Job,
    new_job,
)


class TestVerifyJob:
    def test_new_job_is_pending(self):
        job = new_job()
        assert job.status == JOB_STATUS_PENDING

    def test_fail_sets_incomplete_and_increments(self):
        job = new_job()
        job.fail("one")
        assert job.status == JOB_STATUS_INCOMPLETE
        assert job.failure != ""
        assert job.fail_count == 1

    def test_fail_twice_increments_count(self):
        job = new_job()
        job.fail("one")
        job.fail("two")
        assert job.fail_count == 2

    def test_complete_sets_completed(self):
        job = new_job()
        job.fail("one")
        job.fail("two")
        job.complete()
        assert job.status == JOB_STATUS_COMPLETED


class TestSetNodeId:
    def test_initial_node_id_empty(self):
        job = new_job()
        assert job.node_id == ""

    def test_set_lowercase(self):
        job = new_job()
        job.set_node_id("testing")
        assert job.node_id == "testing"
        assert job.get_node_id() == "testing"

    def test_set_mixed_case_lowered(self):
        job = new_job()
        job.set_node_id("TestingThis")
        assert job.node_id == "testingthis"
        assert job.get_node_id() == "testingthis"

    def test_get_node_id_lowercases_direct_assignment(self):
        job = new_job()
        job.node_id = "TestingThis2"
        assert job.node_id == "TestingThis2"  # Direct set doesn't lowercase
        assert job.get_node_id() == "testingthis2"  # Getter lowercases
        assert job.node_id == "testingthis2"  # Side effect: field is now lowered


class TestGetLegacyNodeId:
    def test_empty_node_id_returns_empty(self):
        job = new_job()
        assert job.get_node_id() == ""

    def test_node_id_lowercased(self):
        job = new_job()
        job.node_id = "Foo"
        assert job.get_node_id() == "foo"

    def test_node_id_takes_precedence_over_legacy(self):
        job = new_job()
        job.node_id = "Foo"
        job.legacy_sensor_id = "Bar"
        assert job.get_node_id() == "foo"

    def test_fallback_to_legacy_sensor_id(self):
        job = new_job()
        job.node_id = ""
        job.legacy_sensor_id = "Bar"
        assert job.get_node_id() == "bar"


class TestCanProcess:
    def test_pending_can_process(self):
        job = new_job()
        assert job.can_process() is True

    def test_incomplete_can_process(self):
        job = new_job()
        job.fail("Something")
        assert job.can_process() is True

    def test_completed_cannot_process(self):
        job = new_job()
        job.fail("Something")
        job.complete()
        assert job.can_process() is False

    def test_deleted_cannot_process(self):
        job = new_job()
        job.status = JOB_STATUS_DELETED
        assert job.can_process() is False


class TestGetKind:
    def test_default_kind(self):
        job = new_job()
        assert job.get_kind() == DEFAULT_JOB_KIND

    def test_custom_kind(self):
        job = new_job()
        job.kind = "foo"
        assert job.get_kind() == "foo"


class TestIsEligibleForRetry:
    def test_first_fail_eligible(self):
        job = new_job()
        job.fail("test failure")
        assert job.is_eligible_for_retry(retry_interval_ms=0, retry_max_attempts=3) is True

    def test_second_fail_still_eligible(self):
        job = new_job()
        job.fail("test failure")
        job.fail("test failure 2")
        assert job.is_eligible_for_retry(retry_interval_ms=0, retry_max_attempts=3) is True

    def test_third_fail_not_eligible(self):
        job = new_job()
        job.fail("test failure")
        job.fail("test failure 2")
        job.fail("test failure 3")
        assert job.is_eligible_for_retry(retry_interval_ms=0, retry_max_attempts=3) is False

    def test_retry_interval_not_elapsed(self):
        job = new_job()
        job.fail("test failure")
        # Fail time is now; 1000ms interval hasn't elapsed
        assert job.is_eligible_for_retry(retry_interval_ms=1000, retry_max_attempts=3) is False

    def test_retry_interval_elapsed(self):
        job = new_job()
        job.fail("test failure")
        # Push fail_time back 1500ms
        job.fail_time = datetime.now(timezone.utc) - timedelta(milliseconds=1500)
        assert job.is_eligible_for_retry(retry_interval_ms=1000, retry_max_attempts=3) is True
