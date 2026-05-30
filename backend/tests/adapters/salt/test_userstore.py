"""Tests for SaltAdminUserstore — manage-user ops via the relay.

Mirrors server/modules/salt/saltstore.go (AddUser..SyncUsers). Email-bearing
operations look up the email from the injected Userstore by user id.
"""

import pytest

from src.adapters.salt.relay import FakeRelayClient
from src.adapters.salt.userstore import SaltAdminUserstore, SaltManageUserError
from src.domain.user import User
from src.ports.users import AdminUserstore

_KNOWN_ID = "11111111-1111-1111-1111-111111111111"
_KNOWN_EMAIL = "user@example.com"


class _FakeUserstore:
    """Minimal Userstore returning a single known user by id."""

    def __init__(self, user: User | None) -> None:
        self._user = user
        self.lookups: list[str] = []

    async def get_users(self) -> list[User]:
        return [self._user] if self._user is not None else []

    async def get_user_by_id(self, user_id: str) -> User | None:
        self.lookups.append(user_id)
        return self._user


class _FakeRolestore:
    """Records scan_now() invocations (the rewrite's Rolestore.Reload())."""

    def __init__(self) -> None:
        self.scan_now_calls = 0

    def scan_now(self) -> None:
        self.scan_now_calls += 1


def _known_user() -> User:
    return User(id=_KNOWN_ID, email=_KNOWN_EMAIL, first_name="Ann", last_name="Lee", note="vip")


def _make_store(
    responses: dict[str, str],
    user: User | None,
) -> tuple[SaltAdminUserstore, FakeRelayClient, _FakeUserstore, _FakeRolestore]:
    relay = FakeRelayClient(responses)
    userstore = _FakeUserstore(user)
    rolestore = _FakeRolestore()
    store = SaltAdminUserstore(relay, userstore, rolestore)
    return store, relay, userstore, rolestore


class TestSatisfiesPort:
    def test_is_an_admin_userstore(self):
        store, _relay, _us, _rs = _make_store({}, None)
        assert isinstance(store, AdminUserstore)


class TestLookupEmailFromId:
    async def test_returns_email_for_matching_user(self):
        store, _relay, _us, _rs = _make_store({}, _known_user())
        assert await store._lookup_email_from_id(_KNOWN_ID) == _KNOWN_EMAIL

    async def test_returns_empty_when_user_is_none(self):
        store, _relay, _us, _rs = _make_store({}, None)
        assert await store._lookup_email_from_id(_KNOWN_ID) == ""

    async def test_returns_empty_when_id_mismatches(self):
        store, _relay, _us, _rs = _make_store({}, User(id="other", email=_KNOWN_EMAIL))
        assert await store._lookup_email_from_id(_KNOWN_ID) == ""


class TestAddUser:
    async def test_sends_add_args_with_first_role(self):
        store, relay, _us, rolestore = _make_store({"manage-user": "true"}, None)
        user = User(
            email=_KNOWN_EMAIL,
            first_name="Ann",
            last_name="Lee",
            note="vip",
            roles=["analyst", "admin"],
        )

        await store.add_user(user)

        assert len(relay.calls) == 1
        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "add",
            "email": _KNOWN_EMAIL,
            "role": "analyst",
            "firstName": "Ann",
            "lastName": "Lee",
            "note": "vip",
            "password": "",
        }
        assert rolestore.scan_now_calls == 1

    async def test_omits_role_when_no_roles(self):
        store, relay, _us, _rs = _make_store({"manage-user": "true"}, None)
        user = User(email=_KNOWN_EMAIL, roles=[])

        await store.add_user(user)

        _command_id, args = relay.calls[0]
        assert "role" not in args
        assert args["operation"] == "add"
        assert args["email"] == _KNOWN_EMAIL

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, None)
        with pytest.raises(SaltManageUserError):
            await store.add_user(User(email=_KNOWN_EMAIL))

    async def test_reloads_even_when_relay_returns_false(self):
        # Go reloads the role map after AddUser regardless of the error
        # (saltstore.go:1277 runs after err is set, before return).
        store, _relay, _us, rolestore = _make_store({"manage-user": "false"}, None)
        with pytest.raises(SaltManageUserError):
            await store.add_user(User(email=_KNOWN_EMAIL))
        assert rolestore.scan_now_calls == 1


class TestDeleteUser:
    async def test_uses_looked_up_email(self):
        store, relay, userstore, _rs = _make_store({"manage-user": "true"}, _known_user())

        await store.delete_user(_KNOWN_ID)

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "delete",
            "email": _KNOWN_EMAIL,
        }
        assert userstore.lookups == [_KNOWN_ID]

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.delete_user(_KNOWN_ID)

    async def test_does_not_reload_on_failure(self):
        # Go's DeleteUser never calls Rolestore.Reload().
        store, _relay, _us, rolestore = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.delete_user(_KNOWN_ID)
        assert rolestore.scan_now_calls == 0


class TestUpdateProfile:
    async def test_uses_looked_up_email_and_profile_fields(self):
        store, relay, _us, _rs = _make_store({"manage-user": "true"}, _known_user())
        user = User(id=_KNOWN_ID, first_name="Bob", last_name="Ng", note="changed")

        await store.update_profile(user)

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "profile",
            "email": _KNOWN_EMAIL,
            "firstName": "Bob",
            "lastName": "Ng",
            "note": "changed",
        }

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.update_profile(User(id=_KNOWN_ID))


class TestResetPassword:
    async def test_uses_looked_up_email_and_password(self):
        store, relay, _us, _rs = _make_store({"manage-user": "true"}, _known_user())

        await store.reset_password(_KNOWN_ID, "s3cret")

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "password",
            "email": _KNOWN_EMAIL,
            "password": "s3cret",
        }

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.reset_password(_KNOWN_ID, "s3cret")


class TestEnableUser:
    async def test_uses_looked_up_email(self):
        store, relay, _us, _rs = _make_store({"manage-user": "true"}, _known_user())

        await store.enable_user(_KNOWN_ID)

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "enable",
            "email": _KNOWN_EMAIL,
        }

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.enable_user(_KNOWN_ID)


class TestDisableUser:
    async def test_uses_looked_up_email(self):
        store, relay, _us, _rs = _make_store({"manage-user": "true"}, _known_user())

        await store.disable_user(_KNOWN_ID)

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "disable",
            "email": _KNOWN_EMAIL,
        }

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.disable_user(_KNOWN_ID)


class TestAddRole:
    async def test_sends_addrole_args_and_reloads(self):
        store, relay, _us, rolestore = _make_store({"manage-user": "true"}, _known_user())

        await store.add_role(_KNOWN_ID, "analyst")

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "addrole",
            "email": _KNOWN_EMAIL,
            "role": "analyst",
        }
        assert rolestore.scan_now_calls == 1

    async def test_bypass_auth_check_param_has_no_behavioral_effect(self):
        store, relay, _us, _rs = _make_store({"manage-user": "true"}, _known_user())

        await store.add_role(_KNOWN_ID, "analyst", bypass_auth_check=True)

        _command_id, args = relay.calls[0]
        assert args["operation"] == "addrole"

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.add_role(_KNOWN_ID, "analyst")

    async def test_reloads_even_when_relay_returns_false(self):
        # Go reloads after AddRole regardless of the error (saltstore.go:1403).
        store, _relay, _us, rolestore = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.add_role(_KNOWN_ID, "analyst")
        assert rolestore.scan_now_calls == 1


class TestDeleteRole:
    async def test_sends_delrole_args_and_reloads(self):
        store, relay, _us, rolestore = _make_store({"manage-user": "true"}, _known_user())

        await store.delete_role(_KNOWN_ID, "analyst")

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-user",
            "operation": "delrole",
            "email": _KNOWN_EMAIL,
            "role": "analyst",
        }
        # Go reloads the role map after DeleteRole (saltstore.go:1425).
        assert rolestore.scan_now_calls == 1

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.delete_role(_KNOWN_ID, "analyst")

    async def test_reloads_even_when_relay_returns_false(self):
        # Go reloads after DeleteRole regardless of the error (saltstore.go:1425).
        store, _relay, _us, rolestore = _make_store({"manage-user": "false"}, _known_user())
        with pytest.raises(SaltManageUserError):
            await store.delete_role(_KNOWN_ID, "analyst")
        assert rolestore.scan_now_calls == 1


class TestSyncUsers:
    async def test_sends_sync_args(self):
        store, relay, _us, _rs = _make_store({"manage-user": "true"}, None)

        await store.sync_users()

        assert len(relay.calls) == 1
        _command_id, args = relay.calls[0]
        assert args == {"command": "manage-user", "operation": "sync"}

    async def test_false_output_raises(self):
        store, _relay, _us, _rs = _make_store({"manage-user": "false"}, None)
        with pytest.raises(SaltManageUserError):
            await store.sync_users()


class TestCommandId:
    async def test_request_id_is_used_when_provided(self):
        relay = FakeRelayClient({"manage-user": "true"})
        store = SaltAdminUserstore(
            relay, _FakeUserstore(None), _FakeRolestore(), request_id="req-7"
        )

        await store.sync_users()

        command_id, _args = relay.calls[0]
        assert command_id == "req-7_manage-user"
