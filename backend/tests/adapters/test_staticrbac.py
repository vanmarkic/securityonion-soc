"""Tests for StaticRBAC adapter — ported from Go staticrbacauthorizer_test.go."""

from pathlib import Path

import pytest

from src.adapters.staticrbac.authorizer import StaticRbacAuthorizer
from src.ports.auth import Unauthorized

FIXTURES = Path(__file__).parent


@pytest.fixture
def auth() -> StaticRbacAuthorizer:
    a = StaticRbacAuthorizer()
    a.init(
        user_files=[str(FIXTURES / "rbac_users.test")],
        role_files=[str(FIXTURES / "rbac_permissions.test"), str(FIXTURES / "rbac_roles.test")],
        scan_interval_ms=60000,
        default_role="defrole",
    )
    a.scan_now()
    return a


class TestIsAuthorized:
    """Ported from Go TestIsAuthorized."""

    def test_role_inheritance(self):
        auth = StaticRbacAuthorizer()
        role_map = {
            "clerk": ["register/operates", "tables/maintains"],
            "baker": ["cakes/bake", "icing/decorates"],
            "chef": ["recipes/create", "menus/create"],
            "henry": ["baker"],
            "tom": ["chef"],
            "alice": [],
        }
        auth.update_role_map(role_map)

        cases = [
            ("henry", "cakes/bake", True),
            ("henry", "pies/bake", False),
            ("henry", "register/operates", False),
            ("alice", "pies/bake", False),
            ("alice", "cakes/bake", False),
            ("alice", "register/operates", False),
            ("tom", "cakes/bake", False),
            ("tom", "recipes/create", True),
            ("tom", "register/operates", False),
        ]
        for subject, permission, expected in cases:
            assert auth.is_authorized(subject, permission) is expected, (
                f"subject={subject}, permission={permission}"
            )


class TestCheckAuthorized:
    def test_missing_user_raises(self, auth: StaticRbacAuthorizer):
        with pytest.raises(Unauthorized):
            auth.check_user_operation_authorized("nonexistent", "action", "resource")

    def test_user_with_permission_passes(self, auth: StaticRbacAuthorizer):
        auth.check_user_operation_authorized("a0-id", "action", "another")

    def test_user_without_permission_raises(self, auth: StaticRbacAuthorizer):
        with pytest.raises(Unauthorized):
            auth.check_user_operation_authorized("a0-id", "action", "some")

    def test_removed_permission(self, auth: StaticRbacAuthorizer):
        auth.check_user_operation_authorized("a1-id", "bar", "foo")
        with pytest.raises(Unauthorized):
            auth.check_user_operation_authorized("a1-id", "action", "another")


class TestCheckAuthorizedProtocol:
    """Test the Authorizer Protocol interface."""

    async def test_protocol_method(self, auth: StaticRbacAuthorizer):
        await auth.check_authorized("a0-id", "action", "another")

    async def test_protocol_method_raises(self, auth: StaticRbacAuthorizer):
        with pytest.raises(Unauthorized):
            await auth.check_authorized("a0-id", "action", "some")


class TestGetRoles:
    def test_returns_role_names(self, auth: StaticRbacAuthorizer):
        roles = auth.get_roles_sync()
        assert "somerole" in roles
        assert "superuser" in roles
        assert "user" in roles

    async def test_protocol_get_roles(self, auth: StaticRbacAuthorizer):
        roles = await auth.get_roles()
        assert "somerole" in roles


class TestGetPermissions:
    async def test_returns_resource_operation_map(self, auth: StaticRbacAuthorizer):
        auth.update_user_map({"a0-id": ["analyst"]})
        permissions = await auth.get_permissions()
        assert "some" in permissions or "another" in permissions or "foo" in permissions


class TestAddRemoveRole:
    def test_add_role_to_user(self, auth: StaticRbacAuthorizer):
        auth.add_role_to_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert "fruity" in roles

    def test_add_duplicate_role(self, auth: StaticRbacAuthorizer):
        auth.add_role_to_user("a1-id", "fruity")
        auth.add_role_to_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert roles.count("fruity") == 1

    def test_remove_role(self, auth: StaticRbacAuthorizer):
        auth.add_role_to_user("a1-id", "fruity")
        auth.remove_role_from_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert "fruity" not in roles

    def test_remove_nonexistent_role(self, auth: StaticRbacAuthorizer):
        auth.remove_role_from_user("a1-id", "fruity")
        roles = auth.get_roles_for_user("a1-id")
        assert "fruity" not in roles


class TestFileParsing:
    def test_parses_role_files(self, auth: StaticRbacAuthorizer):
        assert len(auth._role_map) > 0

    def test_parses_user_files(self, auth: StaticRbacAuthorizer):
        assert "a0-id" in auth._user_map
        assert "a1-id" in auth._user_map


class TestInit:
    def test_zero_scan_interval_raises(self):
        a = StaticRbacAuthorizer()
        with pytest.raises(ValueError):
            a.init(user_files=[], role_files=[], scan_interval_ms=0, default_role="")


class TestEnsureDefaultRole:
    @pytest.mark.skip(
        reason="ensure_default_role_for_user wiring (request context + AdminUserstore, "
        "incl. skip-client + call-count semantics) is deferred to Task 7"
    )
    async def test_new_user_gets_default_role(self, auth: StaticRbacAuthorizer):
        ...
