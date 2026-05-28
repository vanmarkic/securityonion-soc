"""Tests for the /api/playbook/ routes — ported from Go playbookhandler_test.go."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.playbook_routes import (
    get_authorizer,
    get_playbook_service,
    get_request_context_dep,
    router as playbook_router,
)
from src.domain.detection import Detection
from src.domain.playbook import Playbook
from src.ports.auth import Unauthorized
from src.services.playbook_service import PlaybookService
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Fake Playbookstore
# ---------------------------------------------------------------------------

class FakePlaybookstore:
    """In-memory stub implementing the Playbookstore protocol for tests."""

    def __init__(self) -> None:
        self.playbook_to_return: Playbook | None = None
        self.playbooks_to_return: list[Playbook] = []
        self.event_playbooks_to_return: list[Playbook] = []
        self.error: Exception | None = None
        self.event_error: Exception | None = None

    async def get_playbook_by_id(self, playbook_id: str) -> Playbook | None:
        if self.error:
            raise self.error
        return self.playbook_to_return

    async def get_playbooks_for_detection(
        self, detection_id: str, category: str, engine: str,
    ) -> list[Playbook]:
        if self.error:
            raise self.error
        return self.playbooks_to_return

    async def get_event_specific_playbook(
        self, soc_id: str,
    ) -> list[Playbook]:
        if self.event_error:
            raise self.event_error
        if self.error:
            raise self.error
        return self.event_playbooks_to_return


# ---------------------------------------------------------------------------
# Fake Detectionstore
# ---------------------------------------------------------------------------

class FakeDetectionstore:
    """In-memory stub implementing the Detectionstore protocol for tests."""

    def __init__(self) -> None:
        self.detection_to_return: Detection | None = None
        self.error: Exception | None = None

    async def get_detection_by_public_id(self, public_id: str) -> Detection | None:
        if self.error:
            raise self.error
        return self.detection_to_return

    # Satisfy the protocol — unused in playbook tests
    async def create_detection(self, detection: Detection) -> Detection:
        return detection

    async def get_detection(self, detection_id: str) -> Detection:
        return Detection()

    async def update_detection(self, detection: Detection) -> Detection:
        return detection

    async def delete_detection(self, detection_id: str) -> Detection:
        return Detection()

    async def get_detection_history(self, detection_id: str) -> list[Any]:
        return []

    async def create_comment(self, comment: Any) -> Any:
        return comment

    async def get_comment(self, comment_id: str) -> Any:
        return None

    async def get_comments(self, detection_id: str) -> list:
        return []

    async def update_comment(self, comment: Any) -> Any:
        return comment

    async def delete_comment(self, comment_id: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Fake Authorizer
# ---------------------------------------------------------------------------

class FakeAuthorizer:
    """Stub authorizer that can be set to allow or deny."""

    def __init__(self, *, authorized: bool = True) -> None:
        self.authorized = authorized

    async def check_authorized(
        self, user_id: str, operation: str, resource: str,
    ) -> None:
        if not self.authorized:
            raise Unauthorized(user_id, operation, resource)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(
    fake_playbook: FakePlaybookstore,
    fake_detection: FakeDetectionstore,
    *,
    authorized: bool = True,
) -> FastAPI:
    """Build a fresh FastAPI app wired to the fake stores."""
    test_app = FastAPI()
    test_app.include_router(playbook_router, prefix="/api")

    service = PlaybookService(
        playbookstore=fake_playbook,
        detectionstore=fake_detection,
    )
    authorizer = FakeAuthorizer(authorized=authorized)

    test_app.dependency_overrides[get_playbook_service] = lambda: service
    test_app.dependency_overrides[get_authorizer] = lambda: authorizer
    test_app.dependency_overrides[get_request_context_dep] = lambda: RequestContext(
        requestor_id="test-user-id",
        username="test",
    )
    return test_app


@pytest.fixture
def fake_playbook() -> FakePlaybookstore:
    return FakePlaybookstore()


@pytest.fixture
def fake_detection() -> FakeDetectionstore:
    return FakeDetectionstore()


@pytest.fixture
async def client(fake_playbook, fake_detection):
    test_app = _make_app(fake_playbook, fake_detection, authorized=True)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def unauthorized_client(fake_playbook, fake_detection):
    test_app = _make_app(fake_playbook, fake_detection, authorized=False)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# GET /playbook/{id} — TestGetPlaybook (from Go)
# ===========================================================================

class TestGetPlaybook:
    async def test_success_returns_playbook(self, client, fake_playbook):
        """Ported from Go TestGetPlaybook 'Success - Returns playbook'."""
        fake_playbook.playbook_to_return = Playbook(
            name="Test Playbook",
            description="Test Description",
        )
        resp = await client.get("/api/playbook/test-playbook-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Playbook"
        assert data["description"] == "Test Description"

    async def test_missing_playbook_id(self, client):
        """Ported from Go TestGetPlaybook 'Missing playbook ID'.

        Note: FastAPI requires a path param, so this tests the empty string case.
        With an actual empty path, FastAPI returns 404 (route not found).
        """
        resp = await client.get("/api/playbook/")
        # FastAPI will try to match but with trailing slash it goes to /playbook/
        # which doesn't match the route. It returns 404 or redirects.
        assert resp.status_code in (307, 404, 405)

    async def test_unauthorized(self, unauthorized_client):
        """Ported from Go TestGetPlaybook 'Unauthorized'."""
        resp = await unauthorized_client.get("/api/playbook/test-id")
        assert resp.status_code == 403

    async def test_error_retrieving_playbook(self, client, fake_playbook):
        """Ported from Go TestGetPlaybook 'Error retrieving playbook'."""
        fake_playbook.error = Exception("database error")
        resp = await client.get("/api/playbook/error-id")
        assert resp.status_code == 500

    async def test_playbook_not_found_nil(self, client, fake_playbook):
        """Ported from Go TestGetPlaybook 'Playbook not found - nil returned'."""
        fake_playbook.playbook_to_return = None
        resp = await client.get("/api/playbook/non-existent-id")
        assert resp.status_code == 200
        # When nil is returned, the response body should be null/empty
        assert resp.json() is None


# ===========================================================================
# GET /playbook/detection/{id} — TestGetPlaybooksForDetection (from Go)
# ===========================================================================

class TestGetPlaybooksForDetection:
    async def test_success_returns_playbooks(self, client, fake_playbook, fake_detection):
        """Ported from Go TestGetPlaybooksForDetection 'Success - Returns playbooks'."""
        fake_detection.detection_to_return = Detection(
            public_id="test-detection-id",
            category="test-category",
            engine="elastalert",
        )
        fake_playbook.playbooks_to_return = [
            Playbook(name="Playbook 1", description="Description 1"),
            Playbook(name="Playbook 2", description="Description 2"),
        ]
        resp = await client.get("/api/playbook/detection/test-detection-id")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "Playbook 1"
        assert data[0]["description"] == "Description 1"
        assert data[1]["name"] == "Playbook 2"
        assert data[1]["description"] == "Description 2"

    async def test_success_empty_array(self, client, fake_playbook, fake_detection):
        """Ported from Go TestGetPlaybooksForDetection 'Success - Returns empty array'."""
        fake_detection.detection_to_return = Detection(
            public_id="test-detection-id",
            category="test-category",
            engine="elastalert",
        )
        fake_playbook.playbooks_to_return = []
        resp = await client.get("/api/playbook/detection/test-detection-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    async def test_success_raw_yaml_format(self, client, fake_playbook, fake_detection):
        """Ported from Go TestGetPlaybooksForDetection 'Success - Returns raw YAML format'."""
        fake_detection.detection_to_return = Detection(
            public_id="test-detection-id",
            category="test-category",
            engine="elastalert",
        )
        fake_playbook.playbooks_to_return = [
            Playbook(name="Playbook 1", description="Description 1"),
        ]
        resp = await client.get(
            "/api/playbook/detection/test-detection-id",
            params={"raw": "true"},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "name: Playbook 1" in body
        assert "description: Description 1" in body

    async def test_success_multiple_raw_yaml_with_separator(
        self, client, fake_playbook, fake_detection,
    ):
        """Ported from Go TestGetPlaybooksForDetection 'Success - Returns multiple playbooks in raw YAML with separator'."""
        fake_detection.detection_to_return = Detection(
            public_id="test-detection-id",
            category="test-category",
            engine="elastalert",
        )
        fake_playbook.playbooks_to_return = [
            Playbook(name="Playbook 1", description="Description 1"),
            Playbook(name="Playbook 2", description="Description 2"),
        ]
        resp = await client.get(
            "/api/playbook/detection/test-detection-id",
            params={"raw": "true"},
        )
        assert resp.status_code == 200
        body = resp.text
        assert "---" in body
        assert "name: Playbook 1" in body
        assert "name: Playbook 2" in body

    async def test_missing_detection_id(self, client):
        """Ported from Go TestGetPlaybooksForDetection 'Missing detection ID'."""
        # Empty detection_id path - route won't match, returns 404
        resp = await client.get("/api/playbook/detection/")
        assert resp.status_code in (307, 404, 405)

    async def test_unauthorized(self, unauthorized_client):
        """Ported from Go TestGetPlaybooksForDetection 'Unauthorized'."""
        resp = await unauthorized_client.get("/api/playbook/detection/test-id")
        assert resp.status_code == 403

    async def test_detection_not_found(self, client, fake_detection):
        """Ported from Go TestGetPlaybooksForDetection 'Detection not found'."""
        fake_detection.detection_to_return = None
        resp = await client.get("/api/playbook/detection/non-existent-id")
        assert resp.status_code == 404

    async def test_error_retrieving_detection(self, client, fake_detection):
        """Ported from Go TestGetPlaybooksForDetection 'Error retrieving detection'."""
        fake_detection.error = Exception("database error")
        resp = await client.get("/api/playbook/detection/error-id")
        assert resp.status_code == 500

    async def test_error_retrieving_playbooks(
        self, client, fake_playbook, fake_detection,
    ):
        """Ported from Go TestGetPlaybooksForDetection 'Error retrieving playbooks'."""
        fake_detection.detection_to_return = Detection(
            public_id="test-detection-id",
            category="test-category",
            engine="elastalert",
        )
        fake_playbook.error = Exception("playbook retrieval error")
        resp = await client.get("/api/playbook/detection/test-detection-id")
        assert resp.status_code == 500


# ===========================================================================
# GET /playbook/event/{id} — TestGetEventSpecificPlaybook (from Go)
# ===========================================================================

class TestGetEventSpecificPlaybook:
    async def test_success_returns_event_playbooks(self, client, fake_playbook):
        """Ported from Go TestGetEventSpecificPlaybook 'Success - Returns event-specific playbooks'."""
        fake_playbook.event_playbooks_to_return = [
            Playbook(name="Event Playbook 1", description="Event Description 1"),
        ]
        resp = await client.get("/api/playbook/event/test-soc-id")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Event Playbook 1"
        assert data[0]["description"] == "Event Description 1"

    async def test_success_empty_array(self, client, fake_playbook):
        """Ported from Go TestGetEventSpecificPlaybook 'Success - Returns empty array'."""
        fake_playbook.event_playbooks_to_return = []
        resp = await client.get("/api/playbook/event/test-soc-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    async def test_missing_soc_id(self, client):
        """Ported from Go TestGetEventSpecificPlaybook 'Missing SOC ID'."""
        resp = await client.get("/api/playbook/event/")
        assert resp.status_code in (307, 404, 405)

    async def test_unauthorized(self, unauthorized_client):
        """Ported from Go TestGetEventSpecificPlaybook 'Unauthorized'."""
        resp = await unauthorized_client.get("/api/playbook/event/test-id")
        assert resp.status_code == 403

    async def test_event_not_found(self, client, fake_playbook):
        """Ported from Go TestGetEventSpecificPlaybook 'Event not found'."""
        fake_playbook.event_error = Exception("no alert found for soc_id")
        resp = await client.get("/api/playbook/event/non-existent-soc-id")
        assert resp.status_code == 404

    async def test_error_retrieving_event_playbooks(self, client, fake_playbook):
        """Ported from Go TestGetEventSpecificPlaybook 'Error retrieving event playbooks'."""
        fake_playbook.event_error = Exception("database error")
        resp = await client.get("/api/playbook/event/error-id")
        assert resp.status_code == 500
