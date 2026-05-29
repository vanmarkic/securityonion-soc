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


class TestTier1Wiring:
    async def test_roles_endpoint_returns_200(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/roles/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_roles_permissions_endpoint_returns_200(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/roles/permissions")
        assert resp.status_code == 200

    async def test_users_endpoint_returns_200(self, wired_client: AsyncClient):
        resp = await wired_client.get("/api/users/")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # Falls back to StubUserstore (no kratos config) -> 2 dev users
        assert len(body) == 2


# Fixtures copied from the Go staticrbac module live alongside the adapter tests.
_RBAC_FIXTURES = Path(__file__).parent / "adapters"


class TestStaticRbacWiring:
    @pytest.fixture
    async def rbac_client(self, tmp_path: Path):
        from src.main import create_app

        config = {
            "server": {
                "modules": {
                    "statickeyauth": {"apiKey": "k", "anonymousCidr": "*"},
                    "filedatastore": {"jobDir": str(tmp_path / "jobs")},
                    "staticrbac": {
                        "roleFiles": [
                            str(_RBAC_FIXTURES / "rbac_permissions.test"),
                            str(_RBAC_FIXTURES / "rbac_roles.test"),
                        ],
                        "userFiles": [str(_RBAC_FIXTURES / "rbac_users.test")],
                        "scanIntervalMs": 60000,
                        "defaultRole": "",
                    },
                }
            }
        }
        path = tmp_path / "sensoroni.json"
        path.write_text(json.dumps(config))

        app = create_app(str(path))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    async def test_roles_from_files(self, rbac_client: AsyncClient):
        resp = await rbac_client.get("/api/roles/")
        assert resp.status_code == 200
        roles = resp.json()
        # The fixtures define these top-level roles
        assert "somerole" in roles
        assert "superuser" in roles


class TestKratosWiring:
    async def test_kratos_userstore_selected_when_host_configured(self, tmp_path: Path):
        from src.adapters.kratos.userstore import KratosUserstore
        from src.api import users_routes
        from src.main import create_app

        config = {
            "server": {
                "modules": {
                    "statickeyauth": {"apiKey": "k", "anonymousCidr": "*"},
                    "filedatastore": {"jobDir": str(tmp_path / "jobs")},
                    "kratos": {"hostUrl": "http://kratos.invalid:4434"},
                }
            }
        }
        path = tmp_path / "sensoroni.json"
        path.write_text(json.dumps(config))

        app = create_app(str(path))
        factory = app.dependency_overrides[users_routes.get_users_service]
        service = factory()
        assert isinstance(service._userstore, KratosUserstore)
        await service._userstore.close()

    async def test_info_and_users_share_userstore_when_kratos_configured(self, tmp_path: Path):
        from src.adapters.kratos.userstore import KratosUserstore
        from src.api import info_routes, users_routes
        from src.main import create_app

        config = {
            "server": {
                "modules": {
                    "statickeyauth": {"apiKey": "k", "anonymousCidr": "*"},
                    "filedatastore": {"jobDir": str(tmp_path / "jobs")},
                    "kratos": {"hostUrl": "http://kratos.invalid:4434"},
                }
            }
        }
        path = tmp_path / "sensoroni.json"
        path.write_text(json.dumps(config))

        app = create_app(str(path))
        info_svc = app.dependency_overrides[info_routes.get_info_service]()
        users_svc = app.dependency_overrides[users_routes.get_users_service]()
        # Same shared instance — no split-brain
        assert info_svc._userstore is users_svc._userstore
        assert isinstance(info_svc._userstore, KratosUserstore)
        await info_svc._userstore.close()


def _es_config(tmp_path: Path) -> str:
    config = {
        "server": {
            "modules": {
                "statickeyauth": {"apiKey": "k", "anonymousCidr": "*"},
                "filedatastore": {"jobDir": str(tmp_path / "jobs")},
                "elastic": {"hostUrl": "http://localhost:9200", "index": "*:so-*"},
            }
        }
    }
    path = tmp_path / "sensoroni.json"
    path.write_text(json.dumps(config))
    return str(path)


class TestElasticsearchWiring:
    """ES store wiring — no live ES required.

    These tests inspect the installed dependency-override factories and the
    adapter types they build; they never make a network call. Each factory is
    invoked once to construct the store; the underlying AsyncElasticsearch
    clients are closed afterwards so no connector is leaked.
    """

    async def test_create_app_wires_eventstore(self, tmp_path: Path):
        from src.adapters.elasticsearch.eventstore import ElasticEventstore
        from src.api import events_routes
        from src.main import create_app

        app = create_app(_es_config(tmp_path))

        assert events_routes.get_events_service in app.dependency_overrides
        svc = app.dependency_overrides[events_routes.get_events_service]()
        assert isinstance(svc._store, ElasticEventstore)

    async def test_create_app_wires_casestore(self, tmp_path: Path):
        from src.adapters.elasticsearch.casestore import ElasticCasestore
        from src.api import case_routes
        from src.main import create_app

        app = create_app(_es_config(tmp_path))

        assert case_routes.get_case_service in app.dependency_overrides
        svc = app.dependency_overrides[case_routes.get_case_service]()
        assert isinstance(svc._store, ElasticCasestore)

    async def test_create_app_wires_detectionstore(self, tmp_path: Path):
        from src.adapters.elasticsearch.detectionstore import ElasticDetectionstore
        from src.api import detection_routes
        from src.main import create_app

        app = create_app(_es_config(tmp_path))

        assert detection_routes.get_detection_service in app.dependency_overrides
        svc = app.dependency_overrides[detection_routes.get_detection_service]()
        assert isinstance(svc._store, ElasticDetectionstore)

    async def test_create_app_wires_assistantstore(self, tmp_path: Path):
        from src.adapters.elasticsearch.assistantstore import ElasticAssistantstore
        from src.api import assistant_routes
        from src.main import create_app

        app = create_app(_es_config(tmp_path))

        assert assistant_routes.get_assistant_service in app.dependency_overrides
        svc = app.dependency_overrides[assistant_routes.get_assistant_service]()
        assert isinstance(svc._store, ElasticAssistantstore)

    async def test_es_routes_share_one_client_set(self, tmp_path: Path):
        """All four ES stores reuse the same ElasticClients (no pool fan-out)."""
        from src.api import (
            assistant_routes,
            case_routes,
            detection_routes,
            events_routes,
        )
        from src.main import create_app

        app = create_app(_es_config(tmp_path))

        ev = app.dependency_overrides[events_routes.get_events_service]()
        ca = app.dependency_overrides[case_routes.get_case_service]()
        de = app.dependency_overrides[detection_routes.get_detection_service]()
        asst = app.dependency_overrides[assistant_routes.get_assistant_service]()
        assert ev._store._clients is ca._store._clients
        assert ca._store._clients is de._store._clients
        assert de._store._clients is asst._store._clients

    async def test_es_routes_get_auth_request_context(self, tmp_path: Path):
        from src.api import (
            assistant_routes,
            case_routes,
            detection_routes,
            events_routes,
            info_routes,
        )
        from src.main import create_app

        app = create_app(_es_config(tmp_path))

        auth = app.dependency_overrides[info_routes.get_request_context_dep]
        assert app.dependency_overrides[events_routes.get_request_context_dep] is auth
        assert app.dependency_overrides[case_routes.get_request_context_dep] is auth
        assert (
            app.dependency_overrides[detection_routes.get_request_context_dep] is auth
        )
        assert (
            app.dependency_overrides[assistant_routes.get_request_context_dep] is auth
        )

    async def test_module_level_app_stays_override_free(self, tmp_path: Path):
        """create_app must never mutate the shared module-level app."""
        from src.main import app, create_app

        create_app(_es_config(tmp_path))
        assert app.dependency_overrides == {}

    async def test_no_elastic_config_leaves_es_routes_unwired(self, tmp_path: Path):
        """Without an elastic block the ES routes stay un-overridden (Tier-0 only)."""
        from src.api import (
            assistant_routes,
            case_routes,
            detection_routes,
            events_routes,
        )
        from src.main import create_app

        config = {
            "server": {
                "modules": {
                    "statickeyauth": {"apiKey": "k", "anonymousCidr": "*"},
                    "filedatastore": {"jobDir": str(tmp_path / "jobs")},
                }
            }
        }
        path = tmp_path / "sensoroni.json"
        path.write_text(json.dumps(config))

        app = create_app(str(path))
        assert events_routes.get_events_service not in app.dependency_overrides
        assert case_routes.get_case_service not in app.dependency_overrides
        assert detection_routes.get_detection_service not in app.dependency_overrides
        assert assistant_routes.get_assistant_service not in app.dependency_overrides

    async def test_default_create_app_unchanged(self):
        from src.main import create_app

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/health")
            assert resp.status_code == 200
