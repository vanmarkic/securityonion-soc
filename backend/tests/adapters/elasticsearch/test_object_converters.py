"""Tests for the domain-object converters (TASK 9).

Ports ``TestConvertSeverity``, ``TestConvertElasticEventToCase``,
``...Artifact``, ``...ArtifactStream``, ``...Comment``, ``...RelatedEvent``,
``...Detection`` and the ``convertElasticEventToObject`` dispatch from
``server/modules/elastic/converter_test.go``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.adapters.elasticsearch.converter import (
    convert_elastic_event_to_artifact,
    convert_elastic_event_to_artifact_stream,
    convert_elastic_event_to_case,
    convert_elastic_event_to_comment,
    convert_elastic_event_to_detection,
    convert_elastic_event_to_detection_comment,
    convert_elastic_event_to_object,
    convert_elastic_event_to_related_event,
    convert_severity,
)
from src.domain.event import EventRecord


def _rec(payload: dict, id_: str = "abc12") -> EventRecord:
    r = EventRecord()
    r.id = id_
    r.payload = payload
    return r


# --- convert_severity (TestConvertSeverity) --------------------------------


def test_convert_severity():
    assert convert_severity("") == "high"
    assert convert_severity("1") == "low"
    assert convert_severity("2") == "medium"
    assert convert_severity("3") == "high"
    assert convert_severity("4") == "critical"
    assert convert_severity("Critical") == "critical"
    assert convert_severity("unknown") == "unknown"
    assert convert_severity("Low") == "low"
    assert convert_severity("Medium") == "medium"
    assert convert_severity("High") == "high"


# --- case (TestConvertElasticEventToCase) ----------------------------------


def test_convert_case_with_fields():
    rec = _rec(
        {
            "so_kind": "case",
            "so_case.title": "T",
            "so_case.priority": 3.0,
            "so_case.severity": "2",
            "so_case.tags": ["a", "b"],
        }
    )
    c = convert_elastic_event_to_case(rec, "so_")
    assert c is not None
    assert c.title == "T"
    assert c.priority == 3
    assert c.severity == "medium"
    assert c.tags == ["a", "b"]


def test_convert_case_full_fields_and_times():
    my_time = datetime(2021, 12, 20, 12, 43, 0, tzinfo=UTC)
    my_create = my_time - timedelta(hours=1)
    my_complete = my_time - timedelta(hours=2)
    my_start = my_time - timedelta(hours=3)
    rec = _rec(
        {
            "so_kind": "case",
            "so_operation": "update",
            "so_case.title": "myTitle",
            "so_case.description": "myDesc",
            "so_case.priority": 123.0,
            "so_case.severity": "medium",
            "so_case.status": "myStatus",
            "so_case.template": "myTemplate",
            "so_case.userId": "myUserId",
            "so_case.assigneeId": "myAssigneeId",
            "so_case.tlp": "myTlp",
            "so_case.pap": "myPap",
            "so_case.category": "myCategory",
            "so_case.tags": ["tag1", "tag2"],
            "so_case.createTime": my_create,
            "so_case.completeTime": my_complete,
            "so_case.startTime": my_start,
        }
    )
    rec.time = my_time
    c = convert_elastic_event_to_case(rec, "so_")
    assert c is not None
    assert c.kind == "case"
    assert c.operation == "update"
    assert c.title == "myTitle"
    assert c.description == "myDesc"
    assert c.priority == 123
    assert c.severity == "medium"
    assert c.status == "myStatus"
    assert c.template == "myTemplate"
    assert c.user_id == "myUserId"
    assert c.assignee_id == "myAssigneeId"
    assert c.tlp == "myTlp"
    assert c.pap == "myPap"
    assert c.category == "myCategory"
    assert c.update_time == my_time
    assert c.create_time == my_create
    assert c.complete_time == my_complete
    assert c.start_time == my_start


def test_convert_case_nil_tags_safe():
    rec = _rec({"so_kind": "case", "so_operation": "create", "so_case.tags": None})
    c = convert_elastic_event_to_case(rec, "so_")
    assert c is not None
    assert c.tags == []


def test_convert_case_nil_event_returns_none():
    assert convert_elastic_event_to_case(None, "so_") is None


# --- artifact (TestConvertElasticEventToArtifact) --------------------------


def test_convert_artifact_full_fields():
    rec = _rec(
        {
            "so_kind": "artifact",
            "so_operation": "update",
            "so_artifact.value": "myValue",
            "so_artifact.description": "myDesc",
            "so_artifact.streamLength": 123.0,
            "so_artifact.streamId": "myStreamId",
            "so_artifact.groupType": "myGroupType",
            "so_artifact.groupId": "myGroupId",
            "so_artifact.userId": "myUserId",
            "so_artifact.artifactType": "myArtifactType",
            "so_artifact.tlp": "myTlp",
            "so_artifact.mimeType": "myMimeType",
            "so_artifact.ioc": True,
            "so_artifact.md5": "myMd5",
            "so_artifact.sha1": "mySha1",
            "so_artifact.sha256": "mySha256",
            "so_artifact.tags": ["tag1", "tag2"],
        }
    )
    a = convert_elastic_event_to_artifact(rec, "so_")
    assert a is not None
    assert a.kind == "artifact"
    assert a.operation == "update"
    assert a.value == "myValue"
    assert a.description == "myDesc"
    assert a.stream_len == 123
    assert a.stream_id == "myStreamId"
    assert a.group_type == "myGroupType"
    assert a.group_id == "myGroupId"
    assert a.user_id == "myUserId"
    assert a.artifact_type == "myArtifactType"
    assert a.tlp == "myTlp"
    assert a.mime_type == "myMimeType"
    assert a.ioc is True
    assert a.tags == ["tag1", "tag2"]
    assert a.md5 == "myMd5"
    assert a.sha1 == "mySha1"
    assert a.sha256 == "mySha256"


# --- artifact stream (TestConvertElasticEventToArtifactStream) -------------


def test_convert_artifact_stream():
    rec = _rec(
        {
            "so_kind": "artifactstream",
            "so_operation": "create",
            "so_artifactstream.content": "myValue",
            "so_artifactstream.userId": "myUserId",
        }
    )
    s = convert_elastic_event_to_artifact_stream(rec, "so_")
    assert s is not None
    assert s.kind == "artifactstream"
    assert s.operation == "create"
    assert s.user_id == "myUserId"
    assert s.content == "myValue"


# --- comment (TestConvertElasticEventToComment) ----------------------------


def test_convert_comment_fields():
    rec = _rec(
        {
            "so_kind": "comment",
            "so_operation": "create",
            "so_comment.description": "myDesc",
            "so_comment.hours": 1.52,
            "so_comment.userId": "myUserId",
            "so_comment.caseId": "myCaseId",
        }
    )
    c = convert_elastic_event_to_comment(rec, "so_", feat_ttr=True)
    assert c is not None
    assert c.kind == "comment"
    assert c.operation == "create"
    assert c.description == "myDesc"
    assert c.hours == 1.52
    assert c.user_id == "myUserId"
    assert c.case_id == "myCaseId"


def test_convert_comment_hours_gated_off_by_default():
    rec = _rec({"so_kind": "comment", "so_comment.hours": 1.52})
    c = convert_elastic_event_to_comment(rec, "so_")
    assert c is not None
    assert c.hours == 0.0


# --- detection comment -----------------------------------------------------


def test_convert_detection_comment_fields():
    rec = _rec(
        {
            "so_kind": "detectioncomment",
            "so_detectioncomment.value": "myValue",
            "so_detectioncomment.userId": "myUserId",
            "so_detectioncomment.detectionId": "myDetId",
        }
    )
    dc = convert_elastic_event_to_detection_comment(rec, "so_")
    assert dc is not None
    assert dc.value == "myValue"
    assert dc.user_id == "myUserId"
    assert dc.detection_id == "myDetId"


# --- related event (TestConvertElasticEventToRelatedEvent) -----------------


def test_convert_related_event_dynamic_fields():
    rec = _rec(
        {
            "so_kind": "related",
            "so_related.fields.foo": "bar",
            "so_related.caseId": "case1",
        }
    )
    re_ = convert_elastic_event_to_related_event(rec, "so_")
    assert re_ is not None
    assert re_.fields["foo"] == "bar"
    assert re_.case_id == "case1"
    assert len(re_.fields) == 1


# --- detection (TestConvertElasticEventToDetection) ------------------------


def test_convert_detection_flat_fields_and_nested_overrides():
    rec = _rec(
        {
            "so_kind": "detection",
            "so_detection.publicId": "pub-1",
            "so_detection.title": "myTitle",
            "so_detection.severity": "high",
            "so_detection.author": "me",
            "so_detection.isEnabled": True,
            "so_detection.engine": "suricata",
            "so_detection.language": "suricata",
            "so_detection.tags": ["t1", "t2"],
            "so_detection.sourceCreated": "2020-01-02T03:04:05Z",
            "so_detection.overrides": [
                {
                    "type": "suppress",
                    "isEnabled": True,
                    "track": "by_src",
                    "ip": "1.2.3.4",
                    "count": 5.0,
                    "createdAt": "2021-01-02T03:04:05Z",
                }
            ],
        }
    )
    d = convert_elastic_event_to_detection(rec, "so_")
    assert d is not None
    assert d.public_id == "pub-1"
    assert d.title == "myTitle"
    assert d.severity == "high"
    assert d.author == "me"
    assert d.is_enabled is True
    assert d.engine == "suricata"
    assert d.language == "suricata"
    assert d.tags == ["t1", "t2"]
    assert d.source_created is not None
    assert len(d.overrides) == 1
    ov = d.overrides[0]
    assert ov.type == "suppress"
    assert ov.is_enabled is True
    assert ov.override_parameters.track == "by_src"
    assert ov.override_parameters.ip == "1.2.3.4"
    assert ov.override_parameters.count == 5
    assert ov.created_at is not None


# --- dispatch (convertElasticEventToObject) --------------------------------


def test_dispatch_case():
    obj, err = convert_elastic_event_to_object(
        _rec({"so_kind": "case", "so_case.title": "T"}), "so_"
    )
    assert err is None
    assert obj is not None
    assert obj.title == "T"


def test_dispatch_unknown_kind_missing_errors():
    obj, err = convert_elastic_event_to_object(_rec({}, "id77"), "so_")
    assert obj is None
    assert err == "Unknown object kind; id=id77"


def test_dispatch_present_but_unrecognized_returns_none_none():
    obj, err = convert_elastic_event_to_object(_rec({"so_kind": "weird"}), "so_")
    assert obj is None
    assert err is None
