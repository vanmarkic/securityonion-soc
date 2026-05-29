"""Tests for the /api/case/ routes — ported from Go casehandler_test.go."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.case_routes import (
    get_case_service,
    get_request_context_dep,
)
from src.api.case_routes import (
    router as case_router,
)
from src.domain.case import (
    Artifact,
    ArtifactStream,
    Case,
    Comment,
    RelatedEvent,
)
from src.services.case_service import CaseService
from src.shared.context import RequestContext

# ---------------------------------------------------------------------------
# Fake Casestore — stub for testing
# ---------------------------------------------------------------------------

class FakeCasestore:
    """In-memory stub implementing the Casestore protocol for tests."""

    def __init__(self) -> None:
        self.created_cases: list[Case] = []
        self.updated_cases: list[Case] = []
        self.created_comments: list[Comment] = []
        self.updated_comments: list[Comment] = []
        self.created_artifacts: list[Artifact] = []
        self.updated_artifacts: list[Artifact] = []
        self.created_related_events: list[list[RelatedEvent]] = []
        self.deleted_comment_ids: list[str] = []
        self.deleted_event_ids: list[str] = []
        self.deleted_artifact_ids: list[str] = []

        # Configurable return values
        self.case_to_return: Case | None = None
        self.comments_to_return: list[Comment] = []
        self.events_to_return: list[RelatedEvent] = []
        self.artifacts_to_return: list[Artifact] = []
        self.history_to_return: list[Any] = []
        self.artifact_to_return: Artifact | None = None
        self.artifact_stream_to_return: ArtifactStream | None = None
        self.related_events_created_count: int = 0
        self.related_events_err_map: dict[str, str] = {}
        self.related_events_error: str | None = None
        self.error: Exception | None = None

    async def create(self, case: Case) -> Case:
        if self.error:
            raise self.error
        self.created_cases.append(case)
        case.id = "new-case-id"
        return case

    async def update(self, case: Case) -> Case:
        if self.error:
            raise self.error
        self.updated_cases.append(case)
        return case

    async def get_case(self, case_id: str) -> Case | None:
        if self.error:
            raise self.error
        return self.case_to_return

    async def get_case_history(self, case_id: str) -> list[Any]:
        if self.error:
            raise self.error
        return self.history_to_return

    async def create_comment(self, comment: Comment) -> Comment:
        if self.error:
            raise self.error
        self.created_comments.append(comment)
        comment.id = "new-comment-id"
        return comment

    async def get_comment(self, comment_id: str) -> Comment | None:
        if self.error:
            raise self.error
        return None

    async def get_comments(self, case_id: str) -> list[Comment]:
        if self.error:
            raise self.error
        return self.comments_to_return

    async def update_comment(self, comment: Comment) -> Comment:
        if self.error:
            raise self.error
        self.updated_comments.append(comment)
        return comment

    async def delete_comment(self, comment_id: str) -> None:
        if self.error:
            raise self.error
        self.deleted_comment_ids.append(comment_id)

    async def create_related_events(
        self, events: list[RelatedEvent],
    ) -> tuple[int, dict[str, str], None | str]:
        if self.error:
            raise self.error
        self.created_related_events.append(events)
        return (
            self.related_events_created_count,
            self.related_events_err_map,
            self.related_events_error,
        )

    async def get_related_event(self, event_id: str) -> RelatedEvent | None:
        return None

    async def get_related_events(self, case_id: str) -> list[RelatedEvent]:
        if self.error:
            raise self.error
        return self.events_to_return

    async def delete_related_event(self, event_id: str) -> None:
        if self.error:
            raise self.error
        self.deleted_event_ids.append(event_id)

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        if self.error:
            raise self.error
        self.created_artifacts.append(artifact)
        artifact.id = "new-artifact-id"
        return artifact

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        if self.error:
            raise self.error
        return self.artifact_to_return

    async def get_artifacts(
        self, case_id: str, group_type: str, group_id: str,
    ) -> list[Artifact]:
        if self.error:
            raise self.error
        return self.artifacts_to_return

    async def delete_artifact(self, artifact_id: str) -> None:
        if self.error:
            raise self.error
        self.deleted_artifact_ids.append(artifact_id)

    async def update_artifact(self, artifact: Artifact) -> Artifact:
        if self.error:
            raise self.error
        self.updated_artifacts.append(artifact)
        return artifact

    async def create_artifact_stream(self, stream: Any) -> str:
        return "new-stream-id"

    async def get_artifact_stream(self, stream_id: str) -> ArtifactStream | None:
        if self.error:
            raise self.error
        return self.artifact_stream_to_return

    async def delete_artifact_stream(self, stream_id: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(fake_store: FakeCasestore) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake store."""
    test_app = FastAPI()
    test_app.include_router(case_router, prefix="/api")

    service = CaseService(casestore=fake_store)
    test_app.dependency_overrides[get_case_service] = lambda: service
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="11111111-1111-1111-1111-111111111111",
        username="test",
    )
    return test_app


@pytest.fixture
def fake_store() -> FakeCasestore:
    return FakeCasestore()


@pytest.fixture
async def client(fake_store: FakeCasestore):
    test_app = _make_app(fake_store)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# POST /case/ — createCase
# ===========================================================================

class TestCreateCase:
    async def test_create_case_success(self, client, fake_store):
        resp = await client.post("/api/case/", json={"title": "Test Case", "severity": "high"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "new-case-id"
        assert data["title"] == "Test Case"
        assert len(fake_store.created_cases) == 1

    async def test_create_case_invalid_body(self, client):
        resp = await client.post("/api/case/", content=b"not json", headers={"content-type": "application/json"})
        assert resp.status_code == 422

    async def test_create_case_store_error(self, client, fake_store):
        fake_store.error = Exception("database error")
        resp = await client.post("/api/case/", json={"title": "Test"})
        assert resp.status_code == 500


# ===========================================================================
# PUT /case/ — updateCase
# ===========================================================================

class TestUpdateCase:
    async def test_update_case_success(self, client, fake_store):
        resp = await client.put("/api/case/", json={"id": "case-1", "title": "Updated"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated"
        assert len(fake_store.updated_cases) == 1

    async def test_update_case_invalid_body(self, client):
        resp = await client.put("/api/case/", content=b"bad json", headers={"content-type": "application/json"})
        assert resp.status_code == 422

    async def test_update_case_store_error(self, client, fake_store):
        fake_store.error = Exception("update failed")
        resp = await client.put("/api/case/", json={"id": "case-1", "title": "Updated"})
        assert resp.status_code == 500


# ===========================================================================
# GET /case/{id} — getCase
# ===========================================================================

class TestGetCase:
    async def test_get_case_success(self, client, fake_store):
        fake_store.case_to_return = Case(id="case-1", title="Found Case")
        resp = await client.get("/api/case/case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "case-1"
        assert data["title"] == "Found Case"

    async def test_get_case_not_found(self, client, fake_store):
        fake_store.case_to_return = None
        resp = await client.get("/api/case/missing")
        assert resp.status_code == 404

    async def test_get_case_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.get("/api/case/case-1")
        assert resp.status_code == 500


# ===========================================================================
# POST /case/comments — createComment
# ===========================================================================

class TestCreateComment:
    async def test_create_comment_success(self, client, fake_store):
        resp = await client.post(
            "/api/case/comments",
            json={"caseId": "case-1", "description": "A comment"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "new-comment-id"
        assert data["description"] == "A comment"
        assert len(fake_store.created_comments) == 1

    async def test_create_comment_invalid_body(self, client):
        resp = await client.post(
            "/api/case/comments",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_create_comment_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.post(
            "/api/case/comments",
            json={"caseId": "case-1", "description": "A comment"},
        )
        assert resp.status_code == 500


# ===========================================================================
# GET /case/comments/{id} — getComments
# ===========================================================================

class TestGetComments:
    async def test_get_comments_success(self, client, fake_store):
        fake_store.comments_to_return = [
            Comment(id="c1", case_id="case-1", description="Comment 1"),
            Comment(id="c2", case_id="case-1", description="Comment 2"),
        ]
        resp = await client.get("/api/case/comments/case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "c1"
        assert data[1]["id"] == "c2"

    async def test_get_comments_empty(self, client, fake_store):
        fake_store.comments_to_return = []
        resp = await client.get("/api/case/comments/case-1")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_comments_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.get("/api/case/comments/case-1")
        assert resp.status_code == 500


# ===========================================================================
# PUT /case/comments — updateComment
# ===========================================================================

class TestUpdateComment:
    async def test_update_comment_success(self, client, fake_store):
        resp = await client.put(
            "/api/case/comments",
            json={"id": "c1", "caseId": "case-1", "description": "Updated"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated"
        assert len(fake_store.updated_comments) == 1

    async def test_update_comment_invalid_body(self, client):
        resp = await client.put(
            "/api/case/comments",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_update_comment_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.put(
            "/api/case/comments",
            json={"id": "c1", "description": "Updated"},
        )
        assert resp.status_code == 500


# ===========================================================================
# DELETE /case/comments/{id} — deleteComment
# ===========================================================================

class TestDeleteComment:
    async def test_delete_comment_success(self, client, fake_store):
        resp = await client.delete("/api/case/comments/c1")
        assert resp.status_code == 200
        assert "c1" in fake_store.deleted_comment_ids

    async def test_delete_comment_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.delete("/api/case/comments/c1")
        assert resp.status_code == 500


# ===========================================================================
# GET /case/events/{id} — getRelatedEvents
# ===========================================================================

class TestGetRelatedEvents:
    async def test_get_events_success(self, client, fake_store):
        fake_store.events_to_return = [
            RelatedEvent(id="e1", case_id="case-1", fields={"soc_id": "1"}),
            RelatedEvent(id="e2", case_id="case-1", fields={"soc_id": "2"}),
        ]
        resp = await client.get("/api/case/events/case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "e1"

    async def test_get_events_empty(self, client, fake_store):
        fake_store.events_to_return = []
        resp = await client.get("/api/case/events/case-1")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_events_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.get("/api/case/events/case-1")
        assert resp.status_code == 500


# ===========================================================================
# DELETE /case/events/{id} — deleteRelatedEvent
# ===========================================================================

class TestDeleteRelatedEvent:
    async def test_delete_event_success(self, client, fake_store):
        resp = await client.delete("/api/case/events/e1")
        assert resp.status_code == 200
        assert "e1" in fake_store.deleted_event_ids

    async def test_delete_event_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.delete("/api/case/events/e1")
        assert resp.status_code == 500


# ===========================================================================
# POST /case/artifacts — createArtifact
# ===========================================================================

class TestCreateArtifact:
    async def test_create_artifact_success(self, client, fake_store):
        resp = await client.post(
            "/api/case/artifacts",
            json={"caseId": "case-1", "value": "test.exe", "artifactType": "file"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "new-artifact-id"
        assert len(fake_store.created_artifacts) == 1

    async def test_create_artifact_invalid_body(self, client):
        resp = await client.post(
            "/api/case/artifacts",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_create_artifact_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.post(
            "/api/case/artifacts",
            json={"caseId": "case-1", "value": "test.exe"},
        )
        assert resp.status_code == 500


# ===========================================================================
# GET /case/artifacts/{groupType} — getArtifacts
# ===========================================================================

class TestGetArtifacts:
    async def test_get_artifacts_success(self, client, fake_store):
        fake_store.artifacts_to_return = [
            Artifact(id="a1", case_id="case-1", value="file.txt", artifact_type="file"),
        ]
        resp = await client.get("/api/case/artifacts/attachments?id=case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "a1"

    async def test_get_artifacts_empty(self, client, fake_store):
        fake_store.artifacts_to_return = []
        resp = await client.get("/api/case/artifacts/evidence?id=case-1")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_artifacts_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.get("/api/case/artifacts/attachments?id=case-1")
        assert resp.status_code == 500


# ===========================================================================
# PUT /case/artifacts — updateArtifact
# ===========================================================================

class TestUpdateArtifact:
    async def test_update_artifact_success(self, client, fake_store):
        resp = await client.put(
            "/api/case/artifacts",
            json={"id": "a1", "caseId": "case-1", "value": "updated.txt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"] == "updated.txt"
        assert len(fake_store.updated_artifacts) == 1

    async def test_update_artifact_invalid_body(self, client):
        resp = await client.put(
            "/api/case/artifacts",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_update_artifact_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.put(
            "/api/case/artifacts",
            json={"id": "a1", "value": "updated.txt"},
        )
        assert resp.status_code == 500


# ===========================================================================
# DELETE /case/artifacts/{id} — deleteArtifact
# ===========================================================================

class TestDeleteArtifact:
    async def test_delete_artifact_success(self, client, fake_store):
        resp = await client.delete("/api/case/artifacts/a1")
        assert resp.status_code == 200
        assert "a1" in fake_store.deleted_artifact_ids

    async def test_delete_artifact_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.delete("/api/case/artifacts/a1")
        assert resp.status_code == 500


# ===========================================================================
# GET /case/history/{id} — getCaseHistory
# ===========================================================================

class TestGetCaseHistory:
    async def test_get_history_success(self, client, fake_store):
        fake_store.history_to_return = [
            {"id": "h1", "operation": "create"},
            {"id": "h2", "operation": "update"},
        ]
        resp = await client.get("/api/case/history/case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_get_history_not_found(self, client, fake_store):
        fake_store.error = Exception("not found")
        resp = await client.get("/api/case/history/missing")
        assert resp.status_code == 404


# ===========================================================================
# POST /case/events — CreateEvents (async attach, returns 202)
# ===========================================================================

class TestCreateEvents:
    async def test_create_events_returns_202(self, client, fake_store):
        fake_store.related_events_created_count = 2
        resp = await client.post(
            "/api/case/events",
            json={
                "caseId": "case-1",
                "fields": {"soc_id": "event-1"},
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "count" in data

    async def test_create_events_invalid_body(self, client):
        resp = await client.post(
            "/api/case/events",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    async def test_create_events_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.post(
            "/api/case/events",
            json={"caseId": "case-1", "fields": {"soc_id": "e1"}},
        )
        assert resp.status_code == 500


# ===========================================================================
# POST /case/tasks — alias for createArtifact
# ===========================================================================

class TestCreateTask:
    async def test_create_task_success(self, client, fake_store):
        resp = await client.post(
            "/api/case/tasks",
            json={"caseId": "case-1", "value": "malware.exe", "artifactType": "file"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "new-artifact-id"
        assert len(fake_store.created_artifacts) == 1

    async def test_create_task_invalid_body(self, client):
        resp = await client.post(
            "/api/case/tasks",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422


# ===========================================================================
# GET /case/tasks/{id} and GET /case/artifactstream/{id} — artifact stream
# ===========================================================================

class TestGetArtifactStream:
    async def test_get_artifact_stream_via_tasks(self, client, fake_store):
        stream = ArtifactStream()
        stream.write(b"file content here")
        fake_store.artifact_to_return = Artifact(
            id="a1",
            case_id="case-1",
            value="evidence.txt",
            stream_id="stream-1",
            stream_len=17,
            protected=False,
        )
        fake_store.artifact_stream_to_return = stream

        resp = await client.get("/api/case/tasks/a1")
        assert resp.status_code == 200
        assert resp.content == b"file content here"
        assert resp.headers["content-type"] == "application/octet-stream"
        assert 'filename="evidence.txt"' in resp.headers["content-disposition"]

    async def test_get_artifact_stream_via_artifactstream(self, client, fake_store):
        stream = ArtifactStream()
        stream.write(b"binary data")
        fake_store.artifact_to_return = Artifact(
            id="a2",
            case_id="case-1",
            value="capture.pcap",
            stream_id="stream-2",
            stream_len=11,
            protected=False,
        )
        fake_store.artifact_stream_to_return = stream

        resp = await client.get("/api/case/artifactstream/a2")
        assert resp.status_code == 200
        assert resp.content == b"binary data"

    async def test_get_artifact_stream_not_found(self, client, fake_store):
        fake_store.artifact_to_return = None
        resp = await client.get("/api/case/tasks/missing")
        assert resp.status_code == 404

    async def test_get_artifact_stream_via_query_param(self, client, fake_store):
        stream = ArtifactStream()
        stream.write(b"data")
        fake_store.artifact_to_return = Artifact(
            id="a3",
            case_id="case-1",
            value="output.bin",
            stream_id="stream-3",
            stream_len=4,
            protected=False,
        )
        fake_store.artifact_stream_to_return = stream

        resp = await client.get("/api/case/tasks?id=a3")
        assert resp.status_code == 200
        assert resp.content == b"data"


# ===========================================================================
# GET /case/comments — query-param variant (no path param)
# ===========================================================================

class TestGetCommentsQueryParam:
    async def test_get_comments_by_query_param(self, client, fake_store):
        fake_store.comments_to_return = [
            Comment(id="c1", case_id="case-1", description="Comment 1"),
        ]
        resp = await client.get("/api/case/comments?id=case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "c1"


# ===========================================================================
# GET /case/events — query-param variant (no path param)
# ===========================================================================

class TestGetEventsQueryParam:
    async def test_get_events_by_query_param(self, client, fake_store):
        fake_store.events_to_return = [
            RelatedEvent(id="e1", case_id="case-1", fields={"soc_id": "1"}),
        ]
        resp = await client.get("/api/case/events?id=case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "e1"


# ===========================================================================
# GET /case/history — query-param variant (no path param)
# ===========================================================================

class TestGetHistoryQueryParam:
    async def test_get_history_by_query_param(self, client, fake_store):
        fake_store.history_to_return = [
            {"id": "h1", "operation": "create"},
        ]
        resp = await client.get("/api/case/history?id=case-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1


# ===========================================================================
# DELETE /case/tasks/{id} — alias for deleteArtifact
# ===========================================================================

class TestDeleteTask:
    async def test_delete_task_success(self, client, fake_store):
        resp = await client.delete("/api/case/tasks/a1")
        assert resp.status_code == 200
        assert "a1" in fake_store.deleted_artifact_ids

    async def test_delete_task_via_query_param(self, client, fake_store):
        resp = await client.delete("/api/case/tasks?id=a2")
        assert resp.status_code == 200
        assert "a2" in fake_store.deleted_artifact_ids

    async def test_delete_task_store_error(self, client, fake_store):
        fake_store.error = Exception("db error")
        resp = await client.delete("/api/case/tasks/a1")
        assert resp.status_code == 500
