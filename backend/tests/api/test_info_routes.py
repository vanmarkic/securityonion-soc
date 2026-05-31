"""Tests for the /api/info/ route."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.info_routes import get_info_service, get_request_context_dep
from src.domain.info import LicenseKey
from src.domain.user import User
from src.main import app
from src.services.info_service import InfoService
from src.shared.context import RequestContext

GOLDEN_MASTER = Path(__file__).parent.parent / "characterization" / "golden_masters" / "get_api_info.json"


class FakeInfoProvider:
    async def get_version(self) -> str:
        return "unknown"

    async def get_elastic_version(self) -> str:
        return ""

    async def get_license_info(self) -> tuple[str, str, LicenseKey]:
        lk = LicenseKey(
            effective="0001-01-01T00:00:00Z",
            expiration="0001-01-01T00:00:00Z",
            name="",
            id="",
            licensee="",
            features=["api", "fps", "gmd", "lks", "ntf", "odc", "qry", "stg", "ttr", "rpt", "vrt", "oai"],
            users=0,
            nodes=0,
            soc_url="",
            data_url="",
        )
        return "Elastic License 2.0 (ELv2)", "invalid", lk

    async def get_timezones(self) -> list[str]:
        return ["UTC"]

    async def get_parameters(self) -> dict:
        return {}

    async def get_mgmt_mac(self) -> str:
        return "unknown"


class FakeUserstore:
    async def get_users(self) -> list[User]:
        return []

    async def get_user_by_id(self, user_id: str) -> User | None:
        return None


def _fake_info_service() -> InfoService:
    return InfoService(info_provider=FakeInfoProvider(), userstore=FakeUserstore())


def _fake_context() -> RequestContext:
    return RequestContext(requestor_id="test-user-id", username="tester")


@pytest.fixture
async def client():
    app.dependency_overrides[get_info_service] = _fake_info_service
    app.dependency_overrides[get_request_context_dep] = _fake_context
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestInfoRoute:
    async def test_get_info_status_200(self, client):
        resp = await client.get("/api/info/")
        assert resp.status_code == 200

    async def test_get_info_returns_json(self, client):
        resp = await client.get("/api/info/")
        assert resp.headers["content-type"].startswith("application/json")

    async def test_get_info_has_all_golden_master_keys(self, client):
        golden = json.loads(GOLDEN_MASTER.read_text())
        expected_keys = set(golden["response_body"].keys())

        resp = await client.get("/api/info/")
        actual_keys = set(resp.json().keys())
        assert actual_keys == expected_keys

    async def test_get_info_version(self, client):
        resp = await client.get("/api/info/")
        data = resp.json()
        assert data["version"] == "unknown"

    async def test_get_info_user_id(self, client):
        resp = await client.get("/api/info/")
        data = resp.json()
        assert data["userId"] == "test-user-id"

    async def test_get_info_license_key_shape(self, client):
        golden = json.loads(GOLDEN_MASTER.read_text())
        expected_lk_keys = set(golden["response_body"]["licenseKey"].keys())

        resp = await client.get("/api/info/")
        actual_lk_keys = set(resp.json()["licenseKey"].keys())
        assert actual_lk_keys == expected_lk_keys

    async def test_get_info_camel_case_keys(self, client):
        resp = await client.get("/api/info/")
        data = resp.json()
        # Verify camelCase, not snake_case
        assert "elasticVersion" in data
        assert "elastic_version" not in data
        assert "userId" in data
        assert "user_id" not in data
        assert "licenseKey" in data
        assert "license_key" not in data
