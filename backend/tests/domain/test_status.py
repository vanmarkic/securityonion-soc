"""Tests for Status domain model — ported from Go model/status_test.go."""

from src.domain.status import new_status


class TestIsFailureState:
    def test_default_no_failure(self):
        status = new_status("test")
        assert status.detections.elastalert.is_failure_state() is False
        assert status.detections.strelka.is_failure_state() is False
        assert status.detections.suricata.is_failure_state() is False
        assert status.grid_id == "test"

    def test_failure_states(self):
        status = new_status("test")
        status.detections.elastalert.integrity_failure = True
        status.detections.strelka.migration_failure = True
        status.detections.suricata.sync_failure = True
        assert status.detections.elastalert.is_failure_state() is True
        assert status.detections.strelka.is_failure_state() is True
        assert status.detections.suricata.is_failure_state() is True
