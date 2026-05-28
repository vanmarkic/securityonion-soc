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


# ===========================================================================
# PUT /config/ and POST /config/ — putSetting
# ===========================================================================

class TestPutSetting:
    """Ported from Go confighandler putSetting."""

    async def test_put_setting_success(self, client, configstore):
        resp = await client.put(
            "/api/config/",
            json={"id": "elastalert.alerter_parameters", "value": "newval"},
        )
        assert resp.status_code == 200
        assert len(configstore.update_setting_calls) == 1
        setting, remove = configstore.update_setting_calls[0]
        assert setting.id == "elastalert.alerter_parameters"
        assert setting.value == "newval"
        assert remove is False

    async def test_post_setting_success(self, client, configstore):
        resp = await client.post(
            "/api/config/",
            json={"id": "soc.some_setting", "value": "val"},
        )
        assert resp.status_code == 200
        assert len(configstore.update_setting_calls) == 1
        setting, remove = configstore.update_setting_calls[0]
        assert setting.id == "soc.some_setting"
        assert remove is False

    async def test_put_setting_with_node_id(self, client, configstore):
        resp = await client.put(
            "/api/config/",
            json={"id": "soc.setting", "value": "v", "nodeId": "chi-so-001_standalone"},
        )
        assert resp.status_code == 200
        setting, _ = configstore.update_setting_calls[0]
        assert setting.node_id == "chi-so-001_standalone"

    async def test_put_setting_invalid_id(self, client, configstore):
        resp = await client.put(
            "/api/config/",
            json={"id": "invalid id with spaces", "value": "v"},
        )
        assert resp.status_code == 400

    async def test_put_setting_invalid_node_id(self, client, configstore):
        resp = await client.put(
            "/api/config/",
            json={"id": "soc.setting", "value": "v", "nodeId": "bad node id!"},
        )
        assert resp.status_code == 400

    async def test_put_setting_invalid_body(self, client):
        resp = await client.put(
            "/api/config/",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422


# ===========================================================================
# DELETE /config/, /config/{id}, /config/{id}/{minion} — deleteConfig
# ===========================================================================

class TestDeleteConfig:
    """Ported from Go confighandler deleteConfig."""

    async def test_delete_with_path_id(self, client, configstore):
        resp = await client.delete("/api/config/elastalert.alerter_parameters")
        assert resp.status_code == 200
        assert len(configstore.update_setting_calls) == 1
        setting, remove = configstore.update_setting_calls[0]
        assert setting.id == "elastalert.alerter_parameters"
        assert remove is True

    async def test_delete_with_path_id_and_minion(self, client, configstore):
        resp = await client.delete("/api/config/elastalert.alerter_parameters/chi-so-001_standalone")
        assert resp.status_code == 200
        assert len(configstore.update_setting_calls) == 1
        setting, remove = configstore.update_setting_calls[0]
        assert setting.id == "elastalert.alerter_parameters"
        assert setting.node_id == "chi-so-001_standalone"
        assert remove is True

    async def test_delete_with_query_params(self, client, configstore):
        resp = await client.delete("/api/config/?id=soc.setting&minion=node-1")
        assert resp.status_code == 200
        setting, remove = configstore.update_setting_calls[0]
        assert setting.id == "soc.setting"
        assert setting.node_id == "node-1"
        assert remove is True

    async def test_delete_invalid_id(self, client, configstore):
        resp = await client.delete("/api/config/invalid id with spaces")
        assert resp.status_code == 400

    async def test_delete_invalid_minion(self, client, configstore):
        resp = await client.delete("/api/config/soc.setting/bad minion!")
        assert resp.status_code == 400

    async def test_delete_no_id(self, client, configstore):
        resp = await client.delete("/api/config/")
        assert resp.status_code == 400
