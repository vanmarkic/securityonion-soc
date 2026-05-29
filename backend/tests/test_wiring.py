"""Tests that Tier 0 adapter wiring works end-to-end."""

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def config_file(tmp_path: Path) -> str:
    config = {
        "server": {
            "modules": {
                "statickeyauth": {
                    "apiKey": "testkey",
                    "anonymousCidr": "*",
                },
                "filedatastore": {
                    "jobDir": str(tmp_path / "jobs"),
                },
            }
        }
    }
    path = tmp_path / "sensoroni.json"
    path.write_text(json.dumps(config))
    return str(path)


@pytest.fixture
async def wired_client(config_file: str):
    from src.main import create_app

    app = create_app(config_file)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestWiring:
    async def test_health_endpoint(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_info_endpoint_serves_real_response(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/info/")
        assert resp.status_code == 200
        assert "version" in resp.json()

    async def test_jobs_endpoint_serves_empty_list(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/jobs/", params={"kind": ""})
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_grid_endpoint_serves_empty_list(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/grid/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_auth_rejects_bad_key(self, tmp_path: Path):
        from src.main import create_app

        config = {
            "server": {
                "modules": {
                    "statickeyauth": {
                        "apiKey": "secret",
                        "anonymousCidr": "192.168.1.0/24",
                    },
                    "filedatastore": {"jobDir": str(tmp_path / "jobs")},
                }
            }
        }
        path = tmp_path / "sensoroni.json"
        path.write_text(json.dumps(config))

        app = create_app(str(path))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/info/", headers={"Authorization": "wrongkey"})
            assert resp.status_code == 401


class TestDefaultConfig:
    async def test_create_app_with_no_config_boots(self):
        from src.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}
