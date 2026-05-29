"""Tests for Case domain models — ported from Go model/case_test.go."""

from datetime import UTC, datetime

from src.domain.case import (
    new_artifact,
    new_artifact_stream,
    new_case,
    new_related_event,
)


class TestNewRelatedEvent:
    def test_new_related_event_has_create_time(self):
        event = new_related_event()
        assert event.create_time is not None


class TestNewArtifact:
    def test_new_artifact_has_create_time(self):
        artifact = new_artifact()
        assert artifact.create_time is not None


class TestArtifactStreamWrite:
    def test_write_computes_hashes(self):
        stream = new_artifact_stream()
        assert stream.create_time is not None

        content = b"hello world"
        length, mime_type, md5, sha1, sha256 = stream.write(content)

        assert length == 11
        assert mime_type == "text/plain; charset=utf-8"
        assert md5 == "5eb63bbbe01eeed093cb22bb8f5acdc3"
        assert sha1 == "2aae6c35c94fcfb415dbe95f408b9ce91ee846ed"
        assert sha256 == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert stream.content == "aGVsbG8gd29ybGQ="

    def test_read_returns_original_bytes(self):
        stream = new_artifact_stream()
        stream.write(b"hello world")
        assert stream.read() == b"hello world"


class TestProcessWorkflowForStatus:
    def test_new_to_new_no_times(self):
        old_case = new_case()
        new = new_case()
        new.process_workflow_for_status(old_case)
        assert new.complete_time is None
        assert new.start_time is None

    def test_new_to_in_progress_sets_start_time(self):
        old_case = new_case()
        new = new_case()
        new.status = "in progress"
        new.process_workflow_for_status(old_case)
        assert new.complete_time is None
        assert new.start_time is not None

    def test_in_progress_to_closed_sets_complete_time(self):
        old_case = new_case()
        new = new_case()
        # First transition: new -> in progress
        new.status = "in progress"
        new.process_workflow_for_status(old_case)
        assert new.start_time is not None
        start = new.start_time

        # Second transition: in progress -> closed
        new.status = "closed"
        new.process_workflow_for_status(old_case)
        assert new.complete_time is not None
        assert new.complete_time >= start

    def test_preserves_start_time_from_old_case(self):
        now = datetime.now(UTC)
        old_case = new_case()
        old_case.status = "new"
        old_case.start_time = now

        new = new_case()
        new.status = "in progress"
        new.process_workflow_for_status(old_case)
        # Should preserve old start_time, not overwrite
        assert new.start_time == now

    def test_complete_time_updates_on_reclose(self):
        now = datetime.now(UTC)
        old_case = new_case()
        old_case.status = "in progress"
        old_case.complete_time = now

        new = new_case()
        new.status = "closed"
        new.process_workflow_for_status(old_case)
        assert new.complete_time is not None
        assert new.complete_time >= now
