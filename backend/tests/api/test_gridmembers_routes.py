"""Tests for gridmembers routes — ported from Go server/gridmembershandler_test.go."""

import io

from httpx import ASGITransport, AsyncClient

from src.api.gridmembers_routes import get_gridmembers_service
from src.domain.gridmember import GridMember
from src.ports.auth import Authorizer, Unauthorized
from src.services.gridmembers_service import GridMembersService


class FakeGridMembersstore:
    """Stub GridMembersstore for testing."""

    def __init__(self, members: list[GridMember] | None = None) -> None:
        self.members = members or []
        self.manage_calls: list[tuple[str, str]] = []

    async def get_members(self) -> list[GridMember]:
        return self.members

    async def manage_member(self, operation: str, member_id: str) -> None:
        self.manage_calls.append((operation, member_id))


class RejectAuthorizer:
    """Always rejects authorization — matches Go rejectAuthorizer."""

    async def check_authorized(self, user_id: str, operation: str, resource: str) -> None:
        raise Unauthorized(user_id, operation, resource)


class AllowAuthorizer:
    """Always allows authorization."""

    async def check_authorized(self, user_id: str, operation: str, resource: str) -> None:
        pass


def _make_app(
    gridmembersstore: FakeGridMembersstore | None = None,
    authorizer: Authorizer | None = None,
):
    from fastapi import FastAPI

    from src.api.gridmembers_routes import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")

    if gridmembersstore is not None:
        service = GridMembersService(
            gridmembersstore=gridmembersstore,
            authorizer=authorizer or AllowAuthorizer(),
        )
        test_app.dependency_overrides[get_gridmembers_service] = lambda: service
    return test_app


class TestImportAuth:
    """Ported from TestImportAuth — verifies that unauthorized users get 403."""

    async def test_import_rejected_returns_403(self):
        store = FakeGridMembersstore()
        authorizer = RejectAuthorizer()
        test_app = _make_app(gridmembersstore=store, authorizer=authorizer)
        transport = ASGITransport(app=test_app)

        # Build a multipart form with a .pcap file containing valid magic bytes
        # PCAP magic: 0xa1b2c3d4 (big-endian) + 3 extra bytes
        pcap_content = bytes([0xa1, 0xb2, 0xc3, 0xd4, 0x00, 0x00, 0x00])

        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/api/gridmembers/1_standalone/import",
                files={"attachment": ("file.pcap", io.BytesIO(pcap_content), "application/octet-stream")},
            )

        assert resp.status_code == 403
        assert "PERMISSION_DENIED" in resp.text or "not authorized" in resp.text.lower()
