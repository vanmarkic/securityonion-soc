"""Tests for config routes — ported from Go server/confighandler_test.go."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.config_routes import get_config_service
from src.services.config_service import ConfigService


class FakeConfigstore:
    """Stub Configstore that records calls and returns canned results."""

    def __init__(self, *, sync_module_error: Exception | None = None) -> None:
        self.sync_module_error = sync_module_error
        self.sync_module_calls: list[tuple[str, bool]] = []
        self.sync_settings_called = False
        self.get_settings_calls: list[bool] = []
        self.update_setting_calls: list[tuple[object, bool]] = []

    async def get_settings(self, advanced: bool) -> list:
        self.get_settings_calls.append(advanced)
        return []

    async def update_setting(self, setting: object, remove: bool) -> None:
        self.update_setting_calls.append((setting, remove))

    async def sync_settings(self) -> None:
        self.sync_settings_called = True

    async def sync_module(self, module: str, force: bool) -> None:
        self.sync_module_calls.append((module, force))
        if self.sync_module_error is not None:
            raise self.sync_module_error


def _make_app_and_client(configstore: FakeConfigstore | None):
    """Create a fresh FastAPI app with config routes and dependency overrides."""
    from fastapi import FastAPI
    from src.api.config_routes import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")

    if configstore is not None:
        service = ConfigService(configstore=configstore)
        test_app.dependency_overrides[get_config_service] = lambda: service

    return test_app


@pytest.fixture
def configstore():
    return FakeConfigstore()


@pytest.fixture
async def client(configstore):
    test_app = _make_app_and_client(configstore)
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestPutSyncModule:
    """Ported from TestConfigHandler_putSyncModule."""

    async def test_success_without_force(self, client, configstore):
        resp = await client.put("/api/config/sync/soc")
        assert resp.status_code == 200
        assert resp.text == ""
        assert configstore.sync_module_calls == [("soc", False)]

    async def test_success_with_force(self, client, configstore):
        resp = await client.put("/api/config/sync/myapp?force=true")
        assert resp.status_code == 200
        assert resp.text == ""
        assert configstore.sync_module_calls == [("myapp", True)]

    async def test_sync_module_error(self):
        store = FakeConfigstore(sync_module_error=RuntimeError("ERROR_SYNC_FAILED"))
        test_app = _make_app_and_client(store)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.put("/api/config/sync/soc?force=false")
        assert resp.status_code == 500
        assert "ERROR_SYNC_FAILED" in resp.text


class TestPutSyncModuleNoConfigstore:
    """Ported from TestConfigHandler_putSyncModule_NoConfigstore."""

    async def test_no_configstore_returns_405(self):
        test_app = _make_app_and_client(None)
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.put("/api/config/sync/soc")
        assert resp.status_code == 405
        assert "not enabled" in resp.json()["detail"].lower() or "not enabled" in resp.text.lower()
