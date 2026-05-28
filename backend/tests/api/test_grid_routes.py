"""Tests for grid routes — ported from Go server/gridhandler_test.go."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.grid_routes import get_grid_service
from src.domain.node import Node
from src.domain.status import Status
from src.services.grid_service import GridService


class FakeDatastore:
    """Stub Datastore that returns canned nodes."""

    def __init__(self, nodes: list[Node] | None = None) -> None:
        self.nodes = nodes or []

    async def get_nodes(self) -> list[Node]:
        return self.nodes


class FakeStatusstore:
    """Stub Statusstore that returns a canned status."""

    def __init__(self, status: Status | None = None) -> None:
        self.status = status or Status("default-grid-id")

    async def get_status_summary(self) -> Status:
        return self.status


def _make_app(datastore: FakeDatastore, statusstore: FakeStatusstore):
    from fastapi import FastAPI
    from src.api.grid_routes import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")

    service = GridService(datastore=datastore, statusstore=statusstore)
    test_app.dependency_overrides[get_grid_service] = lambda: service

    return test_app


class TestGetStatus:
    """Ported from TestGetStatus — verifies grid ID override on status response."""

    async def test_status_with_assigned_grid_id(self):
        original_status = Status("original-grid-id")
        datastore = FakeDatastore()
        statusstore = FakeStatusstore(status=original_status)
        test_app = _make_app(datastore, statusstore)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/grid/status?assignedGridId=new-grid-id")

        assert resp.status_code == 200
        data = resp.json()
        # Verify the response has the assigned grid ID
        assert data["gridId"] == "new-grid-id"
        # Verify the original status object was NOT modified
        assert original_status.grid_id == "original-grid-id"


class TestGetNodes:
    """Ported from TestGetNodes — verifies grid ID override on node responses."""

    async def test_nodes_with_assigned_grid_id(self):
        original_node = Node("node-1")
        original_node.grid_id = "original-grid-id"

        datastore = FakeDatastore(nodes=[original_node])
        statusstore = FakeStatusstore()
        test_app = _make_app(datastore, statusstore)

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/grid/?assignedGridId=new-grid-id")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        # Verify the response node has the assigned grid ID
        assert data[0]["gridId"] == "new-grid-id"
        # Verify the original node object was NOT modified
        assert original_node.grid_id == "original-grid-id"
