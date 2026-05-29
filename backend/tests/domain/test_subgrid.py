"""Tests for Subgrid domain model — ported from Go model/subgrid_test.go."""

import json

from src.domain.subgrid import Subgrid


class TestSubgridVerify:
    """Ported from TestSubgrid_Verify in subgrid_test.go."""

    def test_valid_subgrid(self):
        grid = Subgrid(
            enabled=True,
            id="test-subgrid",
            manager_url="https://manager.example.com",
            client_id="socl_test_client",
            client_secret="abc",
        )
        assert grid.verify() is None

    def test_empty_id(self):
        grid = Subgrid(
            enabled=True,
            id="",
            manager_url="https://manager.example.com",
            client_id="socl_test_client",
        )
        err = grid.verify()
        assert err == "invalid subgrid ID; must not be empty"

    def test_empty_manager_url(self):
        grid = Subgrid(
            enabled=True,
            id="test-subgrid",
            manager_url="",
            client_id="socl_test_client",
        )
        err = grid.verify()
        assert err == "invalid subgrid Manager URL; must not be empty"

    def test_manager_url_without_https(self):
        grid = Subgrid(
            enabled=True,
            id="test-subgrid",
            manager_url="http://manager.example.com",
            client_id="socl_test_client",
        )
        err = grid.verify()
        assert err == "invalid subgrid Manager URL; must specify the HTTPS protocol"

    def test_empty_client_id(self):
        grid = Subgrid(
            enabled=True,
            id="test-subgrid",
            manager_url="https://manager.example.com",
            client_id="",
        )
        err = grid.verify()
        assert err == "invalid subgrid client ID; must not be empty"

    def test_client_id_without_prefix(self):
        grid = Subgrid(
            enabled=True,
            id="test-subgrid",
            manager_url="https://manager.example.com",
            client_id="test_client",
        )
        err = grid.verify()
        assert err == "invalid subgrid client ID; malformed client ID"

    def test_empty_client_secret(self):
        grid = Subgrid(
            enabled=True,
            id="test-subgrid",
            manager_url="https://manager.example.com",
            client_id="socl_test_client",
            client_secret="",
        )
        err = grid.verify()
        assert err == "invalid subgrid client secret; must not be empty"

    def test_disabled_ignores_empty_secret(self):
        grid = Subgrid(
            enabled=False,
            id="test-subgrid",
            manager_url="https://manager.example.com",
            client_id="socl_test_client",
            client_secret="",
        )
        assert grid.verify() is None


class TestSubgridMarshalJSON:
    """Ported from MarshalJSON behavior in subgrid.go — secret is masked."""

    def test_marshal_masks_client_secret(self):
        grid = Subgrid(
            id="test",
            manager_url="https://example.com",
            client_id="socl_test",
            client_secret="super-secret-value",
            enabled=True,
        )
        data = json.loads(grid.to_json())
        assert data["clientSecret"] == ""
        assert data["id"] == "test"
        assert data["managerUrl"] == "https://example.com"
        assert data["clientId"] == "socl_test"
