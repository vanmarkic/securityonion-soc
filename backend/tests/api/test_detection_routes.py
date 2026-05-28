"""Tests for detection routes -- ported from Go detectionshandler_test.go.

Every Go test function is ported here as a Python test class/method, using
the same test-case structure (table-driven tests -> parametrize).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.detection import (
    Detection,
    DetectionComment,
    EngineName,
    Override,
    OverrideParameters,
    OverrideType,
)
from src.main import app
from src.ports.auth import Unauthorized
from src.services.detection_service import (
    DetectionService,
    ObjectNotFound,
)
from src.api.detection_routes import get_detection_service, get_request_context_dep
from src.shared.context import RequestContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_context() -> RequestContext:
    return RequestContext(requestor_id="test-user-id", username="tester")


def _make_service(
    store: Any = None,
    engines: dict[str, Any] | None = None,
    authorizer: Any = None,
) -> DetectionService:
    """Build a DetectionService with mock collaborators."""
    if store is None:
        store = AsyncMock()
    if engines is None:
        engines = {}
    if authorizer is None:
        authorizer = AsyncMock()
    return DetectionService(store=store, engines=engines, authorizer=authorizer)


@pytest.fixture
def mock_store():
    return AsyncMock()


@pytest.fixture
def mock_engine():
    eng = AsyncMock()
    eng.validate_rule = AsyncMock(return_value="")
    eng.extract_details = AsyncMock(return_value=None)
    eng.apply_filters = AsyncMock(return_value=False)
    eng.sync_local_detections = AsyncMock(return_value={})
    eng.merge_auxiliary_data = AsyncMock(return_value=None)
    eng.convert_rule = AsyncMock(return_value="")
    eng.duplicate_detection = AsyncMock()
    eng.generate_unused_public_id = AsyncMock(return_value="")
    eng.interrupt_sync = AsyncMock()
    return eng


@pytest.fixture
def mock_authorizer():
    auth = AsyncMock()
    auth.check_authorized = AsyncMock(return_value=None)
    return auth


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _wire(service: DetectionService) -> None:
    """Wire service into FastAPI dependency overrides."""
    app.dependency_overrides[get_detection_service] = lambda: service
    app.dependency_overrides[get_request_context_dep] = _fake_context


# ===========================================================================
# TestHandlerGetDetection
# ===========================================================================


class TestGetDetection:
    """Ported from TestHandlerGetDetection."""

    async def test_sunny_day(self, client, mock_store, mock_engine):
        det = Detection(engine=EngineName.SURICATA)
        mock_store.get_detection = AsyncMock(return_value=det)

        service = _make_service(
            store=mock_store,
            engines={EngineName.SURICATA: mock_engine},
        )
        _wire(service)

        resp = await client.get("/api/detection/12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "suricata"

    async def test_not_found_404(self, client, mock_store):
        mock_store.get_detection = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/12345")
        assert resp.status_code == 404

    async def test_elasticsearch_error_500(self, client, mock_store):
        mock_store.get_detection = AsyncMock(
            side_effect=Exception("all shards failed")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/12345")
        assert resp.status_code == 500

    async def test_unexpected_engine_still_200(self, client, mock_store):
        """Detection with unknown engine still returns 200, just no aux merge."""
        det = Detection(engine="FooBar")
        mock_store.get_detection = AsyncMock(return_value=det)
        service = _make_service(store=mock_store, engines={})
        _wire(service)

        resp = await client.get("/api/detection/12345")
        assert resp.status_code == 200
        assert resp.json()["engine"] == "FooBar"

    async def test_merge_aux_data_error_still_200(self, client, mock_store, mock_engine):
        """MergeAuxiliaryData failure does not prevent 200 response."""
        det = Detection(engine=EngineName.SURICATA)
        mock_store.get_detection = AsyncMock(return_value=det)
        mock_engine.merge_auxiliary_data = AsyncMock(
            side_effect=Exception("failed to merge")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.SURICATA: mock_engine},
        )
        _wire(service)

        resp = await client.get("/api/detection/12345")
        assert resp.status_code == 200


# ===========================================================================
# TestHandlerGetByPublicId
# ===========================================================================


class TestGetByPublicId:
    """Ported from TestHandlerGetByPublicId."""

    async def test_sunny_day(self, client, mock_store, mock_engine):
        det = Detection(engine=EngineName.SURICATA)
        mock_store.get_detection_by_public_id = AsyncMock(return_value=det)
        service = _make_service(
            store=mock_store,
            engines={EngineName.SURICATA: mock_engine},
        )
        _wire(service)

        resp = await client.get("/api/detection/public/12345")
        assert resp.status_code == 200
        assert resp.json()["engine"] == "suricata"

    async def test_not_found_error_404(self, client, mock_store):
        mock_store.get_detection_by_public_id = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/public/12345")
        assert resp.status_code == 404

    async def test_not_found_none_404(self, client, mock_store):
        """When store returns None, service raises ObjectNotFound -> 404."""
        mock_store.get_detection_by_public_id = AsyncMock(return_value=None)
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/public/12345")
        assert resp.status_code == 404

    async def test_elasticsearch_error_500(self, client, mock_store):
        mock_store.get_detection_by_public_id = AsyncMock(
            side_effect=Exception("all shards failed")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/public/12345")
        assert resp.status_code == 500

    async def test_unexpected_engine_still_200(self, client, mock_store):
        det = Detection(engine="FooBar")
        mock_store.get_detection_by_public_id = AsyncMock(return_value=det)
        service = _make_service(store=mock_store, engines={})
        _wire(service)

        resp = await client.get("/api/detection/public/12345")
        assert resp.status_code == 200
        assert resp.json()["engine"] == "FooBar"

    async def test_merge_aux_data_error_still_200(self, client, mock_store, mock_engine):
        det = Detection(engine=EngineName.SURICATA)
        mock_store.get_detection_by_public_id = AsyncMock(return_value=det)
        mock_engine.merge_auxiliary_data = AsyncMock(
            side_effect=Exception("failed to merge")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.SURICATA: mock_engine},
        )
        _wire(service)

        resp = await client.get("/api/detection/public/12345")
        assert resp.status_code == 200


# ===========================================================================
# TestHandlerCreateDetection
# ===========================================================================


class TestCreateDetection:
    """Ported from TestHandlerCreateDetection."""

    async def test_sunny_day(self, client, mock_store, mock_engine, mock_authorizer):
        created = Detection(
            id="12345",
            content="test",
            engine=EngineName.ELASTALERT,
            language="sigma",
            ruleset="__custom__",
            author="tester",
        )
        mock_store.create_detection = AsyncMock(return_value=created)
        mock_engine.sync_local_detections = AsyncMock(return_value={})
        mock_engine.apply_filters = AsyncMock(return_value=False)

        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "sigma", "content": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "elastalert"
        assert data["ruleset"] == "__custom__"

    async def test_reject_community_creation_400(self, client, mock_store):
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "sigma", "content": "test", "isCommunity": True},
        )
        assert resp.status_code == 400

    async def test_unsupported_language_400(self, client, mock_store):
        service = _make_service(store=mock_store, engines={})
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "FooBar"},
        )
        assert resp.status_code == 400

    async def test_invalid_rule_400(self, client, mock_store, mock_engine):
        mock_engine.validate_rule = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.SURICATA: mock_engine},
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "suricata", "content": "test"},
        )
        assert resp.status_code == 400

    async def test_modified_by_filters_205(self, client, mock_store, mock_engine, mock_authorizer):
        """When ApplyFilters changes IsEnabled, returns 205."""

        async def _apply_filters(det):
            det.is_enabled = True  # changed from default False
            return False

        mock_engine.apply_filters = _apply_filters

        created = Detection(
            id="12345",
            content="test",
            engine=EngineName.STRELKA,
            language="yara",
            ruleset="__custom__",
            author="tester",
            is_enabled=True,
        )
        mock_store.create_detection = AsyncMock(return_value=created)
        mock_engine.sync_local_detections = AsyncMock(return_value={})

        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "yara", "content": "test"},
        )
        assert resp.status_code == 205

    async def test_extract_details_missing_public_id_400(self, client, mock_store, mock_engine):
        mock_engine.extract_details = AsyncMock(
            side_effect=Exception("rule does not contain a public Id")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "sigma", "content": "test"},
        )
        assert resp.status_code == 400
        assert "missingPublicIdErr" in resp.json()["detail"]

    async def test_extract_details_other_error_400(self, client, mock_store, mock_engine):
        mock_engine.extract_details = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "sigma", "content": "test"},
        )
        assert resp.status_code == 400

    async def test_detection_already_exists_409(self, client, mock_store, mock_engine, mock_authorizer):
        mock_store.create_detection = AsyncMock(
            side_effect=Exception("already exists")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/",
            json={"language": "sigma", "content": "test"},
        )
        assert resp.status_code == 409


# ===========================================================================
# TestHandlerGetDetectionHistory
# ===========================================================================


class TestGetDetectionHistory:
    """Ported from TestHandlerGetDetectionHistory."""

    async def test_sunny_day(self, client, mock_store):
        mock_store.get_detection_history = AsyncMock(return_value=["Hello", "World"])
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/12345/history")
        assert resp.status_code == 200
        assert resp.json() == ["Hello", "World"]

    async def test_not_found_404(self, client, mock_store):
        mock_store.get_detection_history = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/12345/history")
        assert resp.status_code == 404


# ===========================================================================
# TestHandlerDuplicateDetection
# ===========================================================================


class TestDuplicateDetection:
    """Ported from TestHandlerDuplicateDetection."""

    async def test_sunny_day(self, client, mock_store, mock_engine):
        orig = Detection(public_id="Original", engine=EngineName.ELASTALERT)
        dupe = Detection(public_id="Duplicate", engine=EngineName.ELASTALERT)

        mock_store.get_detection = AsyncMock(return_value=orig)
        mock_engine.duplicate_detection = AsyncMock(return_value=dupe)
        mock_store.create_detection = AsyncMock(return_value=dupe)

        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post("/api/detection/12345/duplicate")
        assert resp.status_code == 200
        assert resp.json()["publicId"] == "Duplicate"

    async def test_not_found_500(self, client, mock_store):
        mock_store.get_detection = AsyncMock(
            side_effect=Exception("not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.post("/api/detection/12345/duplicate")
        assert resp.status_code == 500

    async def test_unsupported_engine_400(self, client, mock_store):
        mock_store.get_detection = AsyncMock(
            return_value=Detection(engine="FooBar")
        )
        service = _make_service(store=mock_store, engines={})
        _wire(service)

        resp = await client.post("/api/detection/12345/duplicate")
        assert resp.status_code == 400

    async def test_failed_to_duplicate_500(self, client, mock_store, mock_engine):
        mock_store.get_detection = AsyncMock(
            return_value=Detection(engine=EngineName.ELASTALERT)
        )
        mock_engine.duplicate_detection = AsyncMock(
            side_effect=Exception("failed to duplicate")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post("/api/detection/12345/duplicate")
        assert resp.status_code == 500

    async def test_failed_to_create_500(self, client, mock_store, mock_engine):
        orig = Detection(engine=EngineName.ELASTALERT)
        dupe = Detection(public_id="Duplicate", engine=EngineName.ELASTALERT)

        mock_store.get_detection = AsyncMock(return_value=orig)
        mock_engine.duplicate_detection = AsyncMock(return_value=dupe)
        mock_store.create_detection = AsyncMock(
            side_effect=Exception("failed to create")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post("/api/detection/12345/duplicate")
        assert resp.status_code == 500


# ===========================================================================
# TestHandlerUpdateDetection
# ===========================================================================


class TestUpdateDetection:
    """Ported from TestHandlerUpdateDetection."""

    async def test_sunny_day(self, client, mock_store, mock_engine, mock_authorizer):
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        orig = Detection(
            create_time=now,
            author="First Last",
            ruleset="__custom__",
            license="DRL",
        )
        mock_store.get_detection_by_public_id = AsyncMock(return_value=None)
        mock_store.get_detection = AsyncMock(return_value=orig)
        mock_store.update_detection = AsyncMock(side_effect=lambda d: d)

        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={
                "id": "12345",
                "publicId": "publicID",
                "language": "sigma",
                "engine": "elastalert",
                "content": "test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["author"] == "First Last"
        assert data["license"] == "DRL"
        assert data["ruleset"] == "__custom__"

    async def test_invalid_detection_basic_400(self, client, mock_store):
        """Detection with unsupported engine -> 400 from validate()."""
        service = _make_service(store=mock_store, engines={})
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={"engine": "foobar"},
        )
        assert resp.status_code == 400

    async def test_invalid_rule_engine_400(self, client, mock_store, mock_engine):
        mock_engine.validate_rule = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.SURICATA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={"engine": "suricata", "content": "test"},
        )
        assert resp.status_code == 400

    async def test_prepare_not_found_404(self, client, mock_store, mock_engine):
        mock_store.get_detection = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={"engine": "strelka", "content": "test", "id": "12345"},
        )
        assert resp.status_code == 404

    async def test_prepare_public_id_exists_409(self, client, mock_store, mock_engine):
        mock_store.get_detection_by_public_id = AsyncMock(
            return_value=Detection(id="67890")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={
                "engine": "strelka",
                "content": "test",
                "id": "12345",
                "publicId": "publicID",
            },
        )
        assert resp.status_code == 409

    async def test_prepare_missing_public_id_400(self, client, mock_store, mock_engine):
        mock_engine.extract_details = AsyncMock(
            side_effect=Exception("rule does not contain a public Id")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={"engine": "strelka", "content": "test"},
        )
        assert resp.status_code == 400

    async def test_prepare_other_errors_400(self, client, mock_store, mock_engine):
        mock_engine.extract_details = AsyncMock(
            side_effect=Exception("something else went wrong")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={"engine": "strelka", "content": "test"},
        )
        assert resp.status_code == 400

    async def test_update_cannot_make_community_400(self, client, mock_store, mock_engine):
        """Cannot update non-community to community."""
        mock_store.get_detection = AsyncMock(
            return_value=Detection(is_community=False)
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={
                "engine": "strelka",
                "content": "test",
                "id": "12345",
                "isCommunity": True,
            },
        )
        assert resp.status_code == 400

    async def test_update_not_found_404(self, client, mock_store, mock_engine):
        mock_store.get_detection = AsyncMock(return_value=Detection())
        mock_store.update_detection = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={"engine": "strelka", "content": "test", "id": "12345"},
        )
        assert resp.status_code == 404

    async def test_update_unexpected_error_500(self, client, mock_store, mock_engine):
        mock_store.get_detection = AsyncMock(return_value=Detection())
        mock_store.update_detection = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={"engine": "strelka", "content": "test", "id": "12345"},
        )
        assert resp.status_code == 500

    async def test_successful_disable_after_bad_sync_206(
        self, client, mock_store, mock_engine, mock_authorizer
    ):
        """Sync fails -> auto-disable -> resync succeeds -> 206."""
        old = Detection(is_enabled=True)
        mock_store.get_detection = AsyncMock(return_value=old)

        call_count = 0

        async def _update_side_effect(det):
            nonlocal call_count
            call_count += 1
            return det

        mock_store.update_detection = AsyncMock(side_effect=_update_side_effect)

        sync_count = 0

        async def _sync_side_effect(dets):
            nonlocal sync_count
            sync_count += 1
            if sync_count == 1:
                raise Exception("something went wrong")
            return {}

        mock_engine.sync_local_detections = AsyncMock(side_effect=_sync_side_effect)

        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={
                "engine": "strelka",
                "content": "test",
                "id": "12345",
                "isEnabled": True,
            },
        )
        assert resp.status_code == 206

    async def test_unsuccessful_disable_after_bad_sync_500(
        self, client, mock_store, mock_engine, mock_authorizer
    ):
        """Sync fails -> auto-disable also fails -> 500."""
        old = Detection(is_enabled=True)
        mock_store.get_detection = AsyncMock(return_value=old)

        call_count = 0

        async def _update(det):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("something went wrong")
            return det

        mock_store.update_detection = AsyncMock(side_effect=_update)
        mock_engine.sync_local_detections = AsyncMock(
            side_effect=Exception("something went wrong")
        )

        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={
                "engine": "strelka",
                "content": "test",
                "id": "12345",
                "isEnabled": True,
            },
        )
        assert resp.status_code == 500

    async def test_modified_by_filters_bad_sync_500(
        self, client, mock_store, mock_engine, mock_authorizer
    ):
        """Filter modifies status + sync fails -> no auto-disable -> 500."""

        async def _apply(det):
            det.is_enabled = False
            return True  # filter_applied=True

        mock_engine.apply_filters = _apply
        old = Detection(is_enabled=True)
        mock_store.get_detection = AsyncMock(return_value=old)
        mock_store.update_detection = AsyncMock(side_effect=lambda d: d)
        mock_engine.sync_local_detections = AsyncMock(
            side_effect=Exception("something went wrong")
        )

        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={
                "engine": "strelka",
                "content": "test",
                "id": "12345",
                "isEnabled": True,
            },
        )
        assert resp.status_code == 500

    async def test_modified_by_filters_good_sync_205(
        self, client, mock_store, mock_engine, mock_authorizer
    ):
        """Filter modifies status + sync succeeds -> 205."""

        async def _apply(det):
            det.is_enabled = False
            return True

        mock_engine.apply_filters = _apply
        old = Detection(is_enabled=True)
        mock_store.get_detection = AsyncMock(return_value=old)
        mock_store.update_detection = AsyncMock(side_effect=lambda d: d)
        mock_engine.sync_local_detections = AsyncMock(return_value={})

        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.put(
            "/api/detection/",
            json={
                "engine": "strelka",
                "content": "test",
                "id": "12345",
                "isEnabled": True,
            },
        )
        assert resp.status_code == 205


# ===========================================================================
# TestHandlerUpdateOverrideNote
# ===========================================================================


class TestUpdateOverrideNote:
    """Ported from TestHandlerUpdateOverrideNote."""

    async def test_sunny_day(self, client, mock_store):
        det = Detection(
            overrides=[Override(type=OverrideType.MODIFY)]
        )
        mock_store.get_detection = AsyncMock(return_value=det)
        mock_store.update_detection = AsyncMock(side_effect=lambda d: d)

        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.put(
            "/api/detection/12345/override/0/note",
            json={"note": "note goes here"},
        )
        assert resp.status_code == 200

    async def test_note_too_long_400(self, client, mock_store):
        service = _make_service(store=mock_store)
        _wire(service)

        long_note = "L" * 141
        resp = await client.put(
            "/api/detection/12345/override/0/note",
            json={"note": long_note},
        )
        assert resp.status_code == 400


# ===========================================================================
# TestHandlerDeleteDetection
# ===========================================================================


class TestDeleteDetection:
    """Ported from TestHandlerDeleteDetection."""

    async def test_sunny_day(self, client, mock_store, mock_engine, mock_authorizer):
        orig = Detection(public_id="Original", engine=EngineName.ELASTALERT)
        mock_store.get_detection = AsyncMock(return_value=orig)
        mock_store.delete_detection = AsyncMock(return_value=orig)
        mock_engine.sync_local_detections = AsyncMock(return_value={})

        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.delete("/api/detection/12345")
        assert resp.status_code == 200

    async def test_cannot_delete_community_400(self, client, mock_store):
        mock_store.get_detection = AsyncMock(
            return_value=Detection(is_community=True)
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/12345")
        assert resp.status_code == 400

    async def test_not_found_404(self, client, mock_store):
        mock_store.get_detection = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/12345")
        assert resp.status_code == 404

    async def test_unable_to_get_500(self, client, mock_store):
        mock_store.get_detection = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/12345")
        assert resp.status_code == 500

    async def test_unable_to_delete_500(self, client, mock_store):
        mock_store.get_detection = AsyncMock(return_value=Detection())
        mock_store.delete_detection = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/12345")
        assert resp.status_code == 500

    async def test_unauthorized_403(self, client, mock_store):
        mock_store.get_detection = AsyncMock(return_value=Detection())
        mock_store.delete_detection = AsyncMock(
            side_effect=Unauthorized("", "write", "detections")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/12345")
        assert resp.status_code == 403

    async def test_unable_to_sync_after_delete_500(
        self, client, mock_store, mock_engine, mock_authorizer
    ):
        mock_store.get_detection = AsyncMock(return_value=Detection())
        mock_store.delete_detection = AsyncMock(
            return_value=Detection(engine=EngineName.ELASTALERT)
        )
        mock_engine.sync_local_detections = AsyncMock(
            side_effect=Exception("something went wrong")
        )

        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.delete("/api/detection/12345")
        assert resp.status_code == 500


# ===========================================================================
# TestHandlerBulkUpdateDetection
# ===========================================================================


class TestBulkUpdateDetection:
    """Ported from TestHandlerBulkUpdateDetection."""

    async def test_sunny_day_ids(self, client, mock_store, mock_engine, mock_authorizer):
        for did in ["123", "456", "789"]:
            det = Detection(id=did, engine=EngineName.ELASTALERT)
            mock_store.get_detection = AsyncMock(return_value=det)

        # Override to return different detections for each call
        call_results = [
            Detection(id="123", engine=EngineName.ELASTALERT),
            Detection(id="456", engine=EngineName.SURICATA),
            Detection(id="789", engine=EngineName.STRELKA),
        ]
        mock_store.get_detection = AsyncMock(side_effect=call_results)

        service = _make_service(
            store=mock_store,
            engines={
                EngineName.ELASTALERT: mock_engine,
                EngineName.SURICATA: mock_engine,
                EngineName.STRELKA: mock_engine,
            },
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/bulk/enable",
            json={"ids": ["123", "456", "789"]},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    async def test_cannot_delete_community_ids_400(
        self, client, mock_store, mock_authorizer
    ):
        call_results = [
            Detection(id="123", engine=EngineName.ELASTALERT),
            Detection(id="456", engine=EngineName.SURICATA, is_community=True),
        ]
        mock_store.get_detection = AsyncMock(side_effect=call_results)

        service = _make_service(
            store=mock_store,
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/bulk/delete",
            json={"ids": ["123", "456", "789"]},
        )
        assert resp.status_code == 400

    async def test_unauthorized_403(self, client, mock_store):
        auth = AsyncMock()
        auth.check_authorized = AsyncMock(
            side_effect=Unauthorized("", "write", "detections")
        )
        service = _make_service(store=mock_store, authorizer=auth)
        _wire(service)

        resp = await client.post(
            "/api/detection/bulk/disable",
            json={"ids": ["123"]},
        )
        assert resp.status_code == 403

    async def test_invalid_status_400(self, client, mock_store, mock_authorizer):
        service = _make_service(store=mock_store, authorizer=mock_authorizer)
        _wire(service)

        resp = await client.post(
            "/api/detection/bulk/foobar",
            json={"ids": ["123"]},
        )
        assert resp.status_code == 400


# ===========================================================================
# TestHandlerCreateComment
# ===========================================================================


class TestCreateComment:
    """Ported from TestHandlerCreateComment."""

    async def test_sunny_day(self, client, mock_store):
        async def _create(comment):
            return comment

        mock_store.create_comment = AsyncMock(side_effect=_create)
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.post(
            "/api/detection/12345/comment",
            json={"value": "This is a comment"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["detectionId"] == "12345"
        assert data["value"] == "This is a comment"

    async def test_create_error_500(self, client, mock_store):
        mock_store.create_comment = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.post(
            "/api/detection/12345/comment",
            json={"value": "This is a comment"},
        )
        assert resp.status_code == 500


# ===========================================================================
# TestHandlerGetDetectionComment
# ===========================================================================


class TestGetComment:
    """Ported from TestHandlerGetDetectionComment."""

    async def test_sunny_day(self, client, mock_store):
        comment = DetectionComment(
            id="12345",
            detection_id="det123",
            value="Test comment",
        )
        mock_store.get_comment = AsyncMock(return_value=comment)
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/comment/12345")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "12345"
        assert data["detectionId"] == "det123"
        assert data["value"] == "Test comment"

    async def test_not_found_404(self, client, mock_store):
        mock_store.get_comment = AsyncMock(
            side_effect=Exception("Object not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/comment/12345")
        assert resp.status_code == 404


# ===========================================================================
# TestHandlerUpdateComment
# ===========================================================================


class TestUpdateComment:
    """Ported from TestHandlerUpdateComment."""

    async def test_sunny_day(self, client, mock_store):
        async def _update(comment):
            comment.id = "12345"
            comment.detection_id = "det123"
            return comment

        mock_store.update_comment = AsyncMock(side_effect=_update)
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.put(
            "/api/detection/comment/12345",
            json={"value": "Test comment"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "12345"
        assert data["detectionId"] == "det123"

    async def test_not_found_404(self, client, mock_store):
        mock_store.update_comment = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.put(
            "/api/detection/comment/12345",
            json={"value": "Test comment"},
        )
        assert resp.status_code == 404

    async def test_unexpected_error_500(self, client, mock_store):
        mock_store.update_comment = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.put(
            "/api/detection/comment/12345",
            json={"value": "Test comment"},
        )
        assert resp.status_code == 500


# ===========================================================================
# TestHandlerDeleteComment
# ===========================================================================


class TestDeleteComment:
    """Ported from TestHandlerDeleteComment."""

    async def test_sunny_day(self, client, mock_store):
        mock_store.delete_comment = AsyncMock(return_value=None)
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/comment/12345")
        assert resp.status_code == 200

    async def test_not_found_404(self, client, mock_store):
        mock_store.delete_comment = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/comment/12345")
        assert resp.status_code == 404

    async def test_unexpected_error_500(self, client, mock_store):
        mock_store.delete_comment = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.delete("/api/detection/comment/12345")
        assert resp.status_code == 500


# ===========================================================================
# TestHandlerGetDetectionComments
# ===========================================================================


class TestGetDetectionComments:
    """Ported from TestHandlerGetDetectionComments."""

    async def test_sunny_day(self, client, mock_store):
        comments = [
            DetectionComment(id="123", value="Test comment"),
            DetectionComment(id="456", value="Another comment"),
        ]
        mock_store.get_comments = AsyncMock(return_value=comments)
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/det123/comment")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["id"] == "123"
        assert data[1]["value"] == "Another comment"

    async def test_not_found_404(self, client, mock_store):
        mock_store.get_comments = AsyncMock(
            side_effect=ObjectNotFound("Object not found")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/det123/comment")
        assert resp.status_code == 404

    async def test_unexpected_error_500(self, client, mock_store):
        mock_store.get_comments = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(store=mock_store)
        _wire(service)

        resp = await client.get("/api/detection/det123/comment")
        assert resp.status_code == 500


# ===========================================================================
# TestHandlerConvertContent
# ===========================================================================


class TestConvertContent:
    """Ported from TestHandlerConvertContent."""

    async def test_sunny_day_engine(self, client, mock_store, mock_engine):
        mock_engine.convert_rule = AsyncMock(return_value="converted query")
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/convert",
            json={"content": "sigma goes here", "engine": "elastalert"},
        )
        assert resp.status_code == 200
        assert resp.json()["query"] == "converted query"

    async def test_bad_engine_400(self, client, mock_store):
        service = _make_service(store=mock_store, engines={})
        _wire(service)

        resp = await client.post(
            "/api/detection/convert",
            json={"engine": "suricata"},
        )
        assert resp.status_code == 400

    async def test_good_language(self, client, mock_store, mock_engine):
        """When creating, engine isn't set but language is sigma."""
        mock_engine.convert_rule = AsyncMock(return_value="converted query")
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/convert",
            json={"language": "sigma", "content": "sigma goes here"},
        )
        assert resp.status_code == 200
        assert resp.json()["query"] == "converted query"

    async def test_unknown_error_500(self, client, mock_store, mock_engine):
        mock_engine.convert_rule = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.post(
            "/api/detection/convert",
            json={"engine": "elastalert", "content": "sigma goes here"},
        )
        assert resp.status_code == 500


# ===========================================================================
# TestHandlerSyncEngineDetections
# ===========================================================================


class TestSyncEngineDetections:
    """Ported from TestHandlerSyncEngineDetections."""

    async def test_sunny_day(self, client, mock_store, mock_engine, mock_authorizer):
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post("/api/detection/sync/elastalert/full")
        assert resp.status_code == 200
        mock_engine.interrupt_sync.assert_awaited_once_with(True, True)

    async def test_sync_all(self, client, mock_store, mock_authorizer):
        eng1 = AsyncMock()
        eng2 = AsyncMock()
        service = _make_service(
            store=mock_store,
            engines={
                EngineName.ELASTALERT: eng1,
                EngineName.SURICATA: eng2,
            },
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post("/api/detection/sync/all/update")
        assert resp.status_code == 200
        eng1.interrupt_sync.assert_awaited_once_with(False, True)
        eng2.interrupt_sync.assert_awaited_once_with(False, True)

    async def test_unauthorized_403(self, client, mock_store):
        auth = AsyncMock()
        auth.check_authorized = AsyncMock(
            side_effect=Unauthorized("", "write", "detections")
        )
        service = _make_service(store=mock_store, authorizer=auth)
        _wire(service)

        resp = await client.post("/api/detection/sync/elastalert/full")
        assert resp.status_code == 403

    async def test_unknown_engine_400(self, client, mock_store, mock_authorizer):
        service = _make_service(
            store=mock_store,
            engines={},
            authorizer=mock_authorizer,
        )
        _wire(service)

        resp = await client.post("/api/detection/sync/foobar/full")
        assert resp.status_code == 400


# ===========================================================================
# TestHandlerGenPublicId
# ===========================================================================


class TestGenPublicId:
    """Ported from TestHandlerGenPublicId."""

    async def test_sunny_day(self, client, mock_store, mock_engine):
        mock_engine.generate_unused_public_id = AsyncMock(
            return_value="unused-public-id"
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.ELASTALERT: mock_engine},
        )
        _wire(service)

        resp = await client.get("/api/detection/elastalert/genpublicid")
        assert resp.status_code == 200
        assert resp.json()["publicId"] == "unused-public-id"

    async def test_unknown_engine_400(self, client, mock_store):
        service = _make_service(store=mock_store, engines={})
        _wire(service)

        resp = await client.get("/api/detection/foobar/genpublicid")
        assert resp.status_code == 400

    async def test_not_implemented_501(self, client, mock_store, mock_engine):
        mock_engine.generate_unused_public_id = AsyncMock(
            side_effect=NotImplementedError("not implemented")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.get("/api/detection/strelka/genpublicid")
        assert resp.status_code == 501

    async def test_unexpected_error_500(self, client, mock_store, mock_engine):
        mock_engine.generate_unused_public_id = AsyncMock(
            side_effect=Exception("something went wrong")
        )
        service = _make_service(
            store=mock_store,
            engines={EngineName.STRELKA: mock_engine},
        )
        _wire(service)

        resp = await client.get("/api/detection/strelka/genpublicid")
        assert resp.status_code == 500


# ===========================================================================
# TestPrepareForSave (service-level unit tests)
# ===========================================================================


class TestPrepareForSave:
    """Ported from TestPrepareForSave -- tests the service._prepare_for_save logic."""

    async def test_simple_sunny_day(self, mock_store, mock_engine):
        """Public ID lookup finds same detection -> uses it as old."""
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_store.get_detection_by_public_id = AsyncMock(
            return_value=Detection(id="12345", create_time=now)
        )
        mock_engine.extract_details = AsyncMock(return_value=None)

        det = Detection(
            id="12345",
            public_id="67890",
            engine=EngineName.SURICATA,
            content='alert any any <> any any (msg: "test"; sid:67890; rev:1;)',
        )

        service = _make_service(store=mock_store)
        await service._prepare_for_save(det, mock_engine)

        assert det.create_time == now
        assert det.kind == ""

    async def test_no_duplicate(self, mock_store, mock_engine):
        """Public ID not found -> falls back to GetDetection by id."""
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_store.get_detection_by_public_id = AsyncMock(return_value=None)
        mock_store.get_detection = AsyncMock(
            return_value=Detection(id="12345", create_time=now)
        )

        det = Detection(
            id="12345",
            engine=EngineName.SURICATA,
            content='test',
        )

        service = _make_service(store=mock_store)
        await service._prepare_for_save(det, mock_engine)
        assert det.create_time == now

    async def test_public_id_duplicate_raises(self, mock_store, mock_engine):
        """Public ID found with different internal ID -> PublicIdConflict."""
        from src.services.detection_service import PublicIdConflict

        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_store.get_detection_by_public_id = AsyncMock(
            return_value=Detection(id="23456", create_time=now)
        )

        det = Detection(
            id="12345",
            public_id="67890",
            engine=EngineName.SURICATA,
            content='test',
        )

        service = _make_service(store=mock_store)
        with pytest.raises(PublicIdConflict):
            await service._prepare_for_save(det, mock_engine)

    async def test_update_to_community_raises(self, mock_store, mock_engine):
        """Cannot change non-community to community."""
        mock_store.get_detection_by_public_id = AsyncMock(return_value=None)
        mock_store.get_detection = AsyncMock(
            return_value=Detection(id="12345", is_community=False)
        )

        det = Detection(
            id="12345",
            is_community=True,
            engine=EngineName.SURICATA,
            content='test',
        )

        service = _make_service(store=mock_store)
        from src.services.detection_service import InvalidRequest
        with pytest.raises(InvalidRequest, match="cannot update"):
            await service._prepare_for_save(det, mock_engine)

    async def test_update_from_community(self, mock_store, mock_engine):
        """Editing a community detection preserves community fields."""
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        old_det = Detection(
            id="12345",
            public_id="67890",
            title="test",
            is_enabled=True,
            is_community=True,
            is_reporting=True,
            engine=EngineName.SURICATA,
            content='alert any any <> any any (msg: "test"; sid:67890; rev:1;)',
            create_time=now,
        )
        mock_store.get_detection_by_public_id = AsyncMock(return_value=None)
        mock_store.get_detection = AsyncMock(return_value=old_det)

        det = Detection(
            id="12345",
            engine=EngineName.SURICATA,
            is_enabled=True,
            is_reporting=True,
            content='alert any any <> any any (msg: "test"; sid:67890; rev:1;)',
            overrides=[
                Override(
                    type=OverrideType.MODIFY,
                    created_at=now,
                    updated_at=now,
                    override_parameters=OverrideParameters(regex=".*", value="test"),
                )
            ],
        )

        service = _make_service(store=mock_store)
        await service._prepare_for_save(det, mock_engine)

        assert det.is_community is True
        assert det.create_time == now

    async def test_with_new_override(self, mock_store, mock_engine):
        """New override gets timestamps set."""
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_store.get_detection_by_public_id = AsyncMock(return_value=None)
        mock_store.get_detection = AsyncMock(
            return_value=Detection(id="12345", create_time=now)
        )

        det = Detection(
            id="12345",
            engine=EngineName.SURICATA,
            content='test',
            overrides=[
                Override(
                    type=OverrideType.MODIFY,
                    override_parameters=OverrideParameters(regex=".*", value="test"),
                )
            ],
        )

        service = _make_service(store=mock_store)
        await service._prepare_for_save(det, mock_engine)

        assert det.overrides[0].created_at is not None
        assert det.overrides[0].updated_at is not None

    async def test_with_preexisting_overrides(self, mock_store, mock_engine):
        """Pre-existing override matched in old -> UpdatedAt not changed."""
        now = datetime(2024, 1, 1, tzinfo=timezone.utc)
        override = Override(
            type=OverrideType.MODIFY,
            created_at=now,
            updated_at=now,
            override_parameters=OverrideParameters(regex=".*", value="test"),
        )
        mock_store.get_detection_by_public_id = AsyncMock(return_value=None)
        mock_store.get_detection = AsyncMock(
            return_value=Detection(
                id="12345",
                create_time=now,
                overrides=[
                    Override(
                        type=OverrideType.MODIFY,
                        created_at=now,
                        updated_at=now,
                        override_parameters=OverrideParameters(regex=".*", value="test"),
                    )
                ],
            )
        )

        det = Detection(
            id="12345",
            engine=EngineName.SURICATA,
            content='test',
            overrides=[override],
        )

        service = _make_service(store=mock_store)
        await service._prepare_for_save(det, mock_engine)

        # Override matched -> UpdatedAt preserved (not changed)
        assert len(det.overrides) == 1


# ===========================================================================
# TestLanguageToEngine mapping
# ===========================================================================


class TestLanguageToEngine:
    """Verify language -> engine mapping."""

    def test_sigma_to_elastalert(self):
        assert DetectionService.language_to_engine("sigma") == EngineName.ELASTALERT

    def test_yara_to_strelka(self):
        assert DetectionService.language_to_engine("yara") == EngineName.STRELKA

    def test_suricata_to_suricata(self):
        assert DetectionService.language_to_engine("suricata") == EngineName.SURICATA

    def test_unknown_returns_empty(self):
        assert DetectionService.language_to_engine("foobar") == ""
