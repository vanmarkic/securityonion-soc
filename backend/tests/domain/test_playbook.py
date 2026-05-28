"""Tests for Playbook domain models — ported from Go model/playbook_test.go."""

import json
from datetime import datetime, timezone

import yaml

from src.domain.playbook import ConvertedQuery, EventRecord, Playbook, Question


class TestPlaybookCreation:
    """Ported from TestPlaybookCreation."""

    def test_playbook_fields(self):
        playbook = Playbook(
            name="Test Playbook",
            id="test-playbook-id",
            detection_id="detection-123",
            detection_category="process_creation",
            detection_type="sigma",
            contributors=["SecurityOnionSolutions", "TestUser"],
            questions=[
                Question(
                    question="What process was executed?",
                    context="Understanding the process helps identify malicious activity",
                    range="-1h",
                    answer_sources=["process_creation"],
                    query="Image: {Image}",
                ),
            ],
        )
        assert playbook.name == "Test Playbook"
        assert playbook.id == "test-playbook-id"
        assert playbook.detection_id == "detection-123"
        assert playbook.detection_category == "process_creation"
        assert playbook.detection_type == "sigma"
        assert len(playbook.contributors) == 2
        assert len(playbook.questions) == 1
        assert playbook.questions[0].question == "What process was executed?"


class TestPlaybookJSONSerialization:
    """Ported from TestPlaybookJSONSerialization."""

    def test_json_round_trip(self):
        original = Playbook(
            name="JSON Test Playbook",
            description="Testing JSON serialization",
            id="json-test-id",
            source_created=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            detection_id="json-detection-123",
            detection_category="network_connection",
            detection_type="nids",
            contributors=["TestUser1", "TestUser2"],
            questions=[
                Question(
                    question="What network connections were made?",
                    context="Network connections can indicate C2 activity",
                    range="+/-30m",
                    answer_sources=["network_connection"],
                    query="src_ip: {src_ip} AND dst_ip: {dst_ip}",
                    filled_query="src_ip: 192.168.1.10 AND dst_ip: 10.0.0.1",
                ),
            ],
        )

        json_data = original.model_dump_json(by_alias=True)
        assert "JSON Test Playbook" in json_data
        assert "json-test-id" in json_data
        assert "network_connection" in json_data

        deserialized = Playbook.model_validate_json(json_data)
        assert original.name == deserialized.name
        assert original.id == deserialized.id
        assert original.detection_id == deserialized.detection_id
        assert original.detection_category == deserialized.detection_category
        assert original.detection_type == deserialized.detection_type
        assert original.contributors == deserialized.contributors
        assert len(deserialized.questions) == 1
        assert original.questions[0].question == deserialized.questions[0].question
        assert original.questions[0].context == deserialized.questions[0].context
        assert original.questions[0].range == deserialized.questions[0].range


class TestPlaybookYAMLSerialization:
    """Ported from TestPlaybookYAMLSerialization."""

    def test_yaml_round_trip(self):
        original = Playbook(
            name="YAML Test Playbook",
            description="Testing YAML serialization",
            id="yaml-test-id",
            source_created=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            detection_id="yaml-detection-123",
            detection_category="file_event",
            detection_type="sigma",
            contributors=["YAMLTestUser"],
            questions=[
                Question(
                    question="What files were accessed?",
                    context="File access patterns can reveal malicious behavior",
                    range="-2h",
                    answer_sources=["file_event"],
                    query="TargetFilename: {TargetFilename}",
                ),
            ],
        )

        yaml_data = yaml.dump(original.model_dump(by_alias=True))
        assert "YAML Test Playbook" in yaml_data
        assert "yaml-test-id" in yaml_data
        assert "file_event" in yaml_data

        loaded = yaml.safe_load(yaml_data)
        deserialized = Playbook.model_validate(loaded)
        assert original.name == deserialized.name
        assert original.id == deserialized.id
        assert original.detection_id == deserialized.detection_id
        assert original.detection_category == deserialized.detection_category
        assert original.detection_type == deserialized.detection_type
        assert original.contributors == deserialized.contributors
        assert len(deserialized.questions) == 1
        assert original.questions[0].question == deserialized.questions[0].question


class TestQuestionCreation:
    """Ported from TestQuestionCreation."""

    def test_all_fields(self):
        question = Question(
            question="What is the source IP?",
            context="Source IP helps identify the origin of the attack",
            range="+/-1h",
            answer_sources=["network", "alert"],
            query="src_ip: {src_ip}",
            filled_query="src_ip: 192.168.1.100",
            query_results=[
                EventRecord(
                    id="event-1",
                    payload={
                        "src_ip": "192.168.1.100",
                        "dst_ip": "10.0.0.1",
                    },
                ),
            ],
            query_fields=["src_ip", "dst_ip", "timestamp"],
            oql_query="src_ip: 192.168.1.100",
        )

        assert question.question == "What is the source IP?"
        assert question.context == "Source IP helps identify the origin of the attack"
        assert question.range == "+/-1h"
        assert len(question.answer_sources) == 2
        assert "network" in question.answer_sources
        assert "alert" in question.answer_sources
        assert question.query == "src_ip: {src_ip}"
        assert question.filled_query == "src_ip: 192.168.1.100"
        assert len(question.query_results) == 1
        assert question.query_results[0].id == "event-1"
        assert len(question.query_fields) == 3
        assert question.oql_query == "src_ip: 192.168.1.100"


class TestQuestionWithNilRange:
    """Ported from TestQuestionWithNilRange."""

    def test_nil_range(self):
        question = Question(
            question="What is the alert content?",
            range=None,
            answer_sources=["alert"],
        )
        assert question.question == "What is the alert content?"
        assert question.range is None
        assert len(question.answer_sources) == 1
        assert question.answer_sources[0] == "alert"


class TestConvertedQueryCreation:
    """Ported from TestConvertedQueryCreation."""

    def test_fields(self):
        cq = ConvertedQuery(
            query="hostname: test-host AND user.name: admin",
            fields=["hostname", "user.name", "process.name", "command_line"],
        )
        assert cq.query == "hostname: test-host AND user.name: admin"
        assert len(cq.fields) == 4
        assert "hostname" in cq.fields
        assert "user.name" in cq.fields
        assert "process.name" in cq.fields
        assert "command_line" in cq.fields


class TestConvertedQueryJSONSerialization:
    """Ported from TestConvertedQueryJSONSerialization."""

    def test_json_round_trip(self):
        original = ConvertedQuery(
            query="src_ip: 10.0.0.1 AND dst_port: 443",
            fields=["src_ip", "dst_ip", "dst_port", "protocol"],
        )

        json_data = original.model_dump_json()
        assert "src_ip: 10.0.0.1 AND dst_port: 443" in json_data
        assert "src_ip" in json_data
        assert "dst_port" in json_data

        deserialized = ConvertedQuery.model_validate_json(json_data)
        assert original.query == deserialized.query
        assert original.fields == deserialized.fields


class TestPlaybookDetectionTypes:
    """Ported from TestPlaybookDetectionTypes."""

    def test_nids_type(self):
        pb = Playbook(detection_type="nids", id="detection-type-test-nids")
        assert pb.detection_type == "nids"

    def test_sigma_type(self):
        pb = Playbook(detection_type="sigma", id="detection-type-test-sigma")
        assert pb.detection_type == "sigma"

    def test_yara_type(self):
        pb = Playbook(detection_type="yara", id="detection-type-test-yara")
        assert pb.detection_type == "yara"

    def test_empty_type(self):
        pb = Playbook(detection_type="", id="detection-type-test-empty")
        assert pb.detection_type == ""

    def test_case_insensitive_nids(self):
        pb = Playbook(detection_type="NIDS", id="detection-type-test-NIDS")
        assert pb.detection_type == "NIDS"

    def test_case_insensitive_sigma(self):
        pb = Playbook(detection_type="SIGMA", id="detection-type-test-SIGMA")
        assert pb.detection_type == "SIGMA"


class TestPlaybookWithMultipleQuestions:
    """Ported from TestPlaybookWithMultipleQuestions."""

    def test_four_questions(self):
        playbook = Playbook(
            name="Multi-Question Playbook",
            id="multi-question-test",
            questions=[
                Question(
                    question="What process triggered the alert?",
                    context="Identify the initial process",
                    range=None,
                    answer_sources=["process_creation"],
                    query="ProcessGuid: {ProcessGuid}",
                ),
                Question(
                    question="What child processes were spawned?",
                    context="Identify subsequent malicious activity",
                    range="+5m",
                    answer_sources=["process_creation"],
                    query="ParentProcessGuid: {ProcessGuid}",
                ),
                Question(
                    question="What files were accessed?",
                    context="Identify file system impact",
                    range="+/-10m",
                    answer_sources=["file_event"],
                    query="ProcessGuid: {ProcessGuid}",
                ),
                Question(
                    question="What network connections were made?",
                    context="Identify network-based indicators",
                    range="+/-15m",
                    answer_sources=["network_connection"],
                    query="ProcessGuid: {ProcessGuid}",
                ),
            ],
        )

        assert playbook.name == "Multi-Question Playbook"
        assert len(playbook.questions) == 4

        # First question (no range)
        assert playbook.questions[0].question == "What process triggered the alert?"
        assert playbook.questions[0].range is None
        assert "process_creation" in playbook.questions[0].answer_sources

        # Second question (forward range)
        assert playbook.questions[1].question == "What child processes were spawned?"
        assert playbook.questions[1].range == "+5m"

        # Third question (bidirectional range)
        assert playbook.questions[2].question == "What files were accessed?"
        assert playbook.questions[2].range == "+/-10m"
        assert "file_event" in playbook.questions[2].answer_sources

        # Fourth question (longer bidirectional range)
        assert playbook.questions[3].question == "What network connections were made?"
        assert playbook.questions[3].range == "+/-15m"
        assert "network_connection" in playbook.questions[3].answer_sources


class TestPlaybookWithSourceTimestamps:
    """Ported from TestPlaybookWithSourceTimestamps."""

    def test_created_and_modified(self):
        created = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        modified = datetime(2024, 1, 16, 15, 30, 0, tzinfo=timezone.utc)

        playbook = Playbook(
            source_created=created,
            source_updated=modified,
            id="timestamp-test",
        )

        assert playbook.source_created == created
        assert playbook.source_updated is not None
        assert playbook.source_updated == modified
        assert playbook.source_updated > playbook.source_created


class TestPlaybookWithoutSourceUpdated:
    """Ported from TestPlaybookWithoutSourceUpdated."""

    def test_nil_source_updated(self):
        playbook = Playbook(
            source_created=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            source_updated=None,
            id="no-update-test",
        )

        assert playbook.source_created != datetime.min
        assert playbook.source_updated is None


class TestQuestionWithQueryResults:
    """Ported from TestQuestionWithQueryResults."""

    def test_multiple_results(self):
        event_results = [
            EventRecord(
                id="result-1",
                payload={
                    "Image": "notepad.exe",
                    "CommandLine": "notepad.exe document.txt",
                    "User": "DOMAIN\\user1",
                },
            ),
            EventRecord(
                id="result-2",
                payload={
                    "Image": "cmd.exe",
                    "CommandLine": "cmd.exe /c dir",
                    "User": "DOMAIN\\user1",
                },
            ),
        ]

        question = Question(
            query_results=event_results,
            query_fields=["Image", "CommandLine", "User", "ProcessGuid"],
        )

        assert len(question.query_results) == 2
        assert question.query_results[0].id == "result-1"
        assert question.query_results[1].id == "result-2"
        assert question.query_results[0].payload["Image"] == "notepad.exe"
        assert question.query_results[1].payload["Image"] == "cmd.exe"
        assert len(question.query_fields) == 4
        assert "Image" in question.query_fields
        assert "CommandLine" in question.query_fields
        assert "User" in question.query_fields
        assert "ProcessGuid" in question.query_fields


class TestPlaybookEngineSpecificFields:
    """Ported from TestPlaybookEngineSpecificFields."""

    def test_suricata_nids(self):
        pb = Playbook(
            detection_type="nids",
            detection_category="ET SCAN",
            id="engine-test-nids",
        )
        assert pb.detection_type == "nids"
        assert pb.detection_category == "ET SCAN"

    def test_sigma_process_creation(self):
        pb = Playbook(
            detection_type="sigma",
            detection_category="process_creation",
            id="engine-test-sigma",
        )
        assert pb.detection_type == "sigma"
        assert pb.detection_category == "process_creation"

    def test_yara_file_analysis(self):
        pb = Playbook(
            detection_type="yara",
            detection_category="file_event",
            id="engine-test-yara",
        )
        assert pb.detection_type == "yara"
        assert pb.detection_category == "file_event"

    def test_generic(self):
        pb = Playbook(
            detection_type="",
            detection_category="generic",
            id="engine-test-generic",
        )
        assert pb.detection_type == ""
        assert pb.detection_category == "generic"


class TestEmptyPlaybook:
    """Ported from TestEmptyPlaybook."""

    def test_all_defaults(self):
        playbook = Playbook()

        assert playbook.name == ""
        assert playbook.description == ""
        assert playbook.id == ""
        assert playbook.source_created is None
        assert playbook.source_updated is None
        assert playbook.detection_id == ""
        assert playbook.detection_category == ""
        assert playbook.detection_type == ""
        assert playbook.contributors is None
        assert playbook.questions is None


class TestEmptyQuestion:
    """Ported from TestEmptyQuestion."""

    def test_all_defaults(self):
        question = Question()

        assert question.question == ""
        assert question.context == ""
        assert question.range is None
        assert question.answer_sources is None
        assert question.query == ""
        assert question.filled_query == ""
        assert question.query_results is None
        assert question.query_fields is None
        assert question.oql_query == ""


class TestEmptyConvertedQuery:
    """Ported from TestEmptyConvertedQuery."""

    def test_all_defaults(self):
        cq = ConvertedQuery()

        assert cq.query == ""
        assert cq.fields is None
