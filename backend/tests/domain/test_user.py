"""Tests for the User domain model and Userstore port."""

from src.domain.user import User
from src.ports.users import Userstore


class TestUser:
    def test_create_user(self):
        user = User(
            id="user-1",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
            note="",
            roles=["analyst"],
            status="active",
            totp_status="disabled",
            webauthn_status="disabled",
        )
        assert user.id == "user-1"
        assert user.email == "alice@example.com"
        assert user.first_name == "Alice"
        assert user.roles == ["analyst"]

    def test_user_camel_case_serialization(self):
        user = User(
            id="user-1",
            email="alice@example.com",
            first_name="Alice",
            last_name="Smith",
            note="",
            roles=["analyst"],
            status="active",
            totp_status="disabled",
            webauthn_status="disabled",
        )
        data = user.model_dump(by_alias=True)
        assert "firstName" in data
        assert "lastName" in data
        assert "totpStatus" in data
        assert "webauthnStatus" in data
        assert "first_name" not in data

    def test_user_populate_by_name(self):
        user = User(
            id="u2",
            email="bob@example.com",
            firstName="Bob",
            lastName="Jones",
            note="",
            roles=[],
            status="locked",
            totpStatus="enabled",
            webauthnStatus="enabled",
        )
        assert user.first_name == "Bob"
        assert user.totp_status == "enabled"


class FakeUserstore:
    """A fake that must satisfy Userstore protocol."""

    def __init__(self):
        self._users = [
            User(
                id="user-1",
                email="alice@example.com",
                first_name="Alice",
                last_name="Smith",
                note="",
                roles=["analyst"],
                status="active",
                totp_status="disabled",
                webauthn_status="disabled",
            )
        ]

    async def get_users(self) -> list[User]:
        return self._users

    async def get_user_by_id(self, user_id: str) -> User | None:
        for u in self._users:
            if u.id == user_id:
                return u
        return None


class TestUserstore:
    def test_fake_satisfies_protocol(self):
        store: Userstore = FakeUserstore()
        assert isinstance(store, Userstore)

    async def test_get_users(self):
        store: Userstore = FakeUserstore()
        users = await store.get_users()
        assert len(users) == 1
        assert users[0].email == "alice@example.com"

    async def test_get_user_by_id_found(self):
        store: Userstore = FakeUserstore()
        user = await store.get_user_by_id("user-1")
        assert user is not None
        assert user.first_name == "Alice"

    async def test_get_user_by_id_not_found(self):
        store: Userstore = FakeUserstore()
        user = await store.get_user_by_id("nonexistent")
        assert user is None


class TestUserVerify:
    def test_empty_user_is_valid(self):
        user = User()
        assert user.verify() is None

    def test_id_too_long(self):
        user = User(id="x" * 150)
        err = user.verify()
        assert err is not None
        assert "ERROR_USER_ID_TOO_LONG" in str(err)

    def test_id_at_limit_is_valid(self):
        user = User(id="a" * 36)
        assert user.verify() is None

    def test_first_name_too_long(self):
        user = User(first_name="x" * 150)
        err = user.verify()
        assert err is not None
        assert "ERROR_FIRSTNAME_TOO_LONG" in str(err)

    def test_last_name_too_long(self):
        user = User(last_name="x" * 150)
        err = user.verify()
        assert err is not None
        assert "ERROR_LASTNAME_TOO_LONG" in str(err)

    def test_note_too_long(self):
        user = User(note="x" * 150)
        err = user.verify()
        assert err is not None
        assert "ERROR_NOTE_TOO_LONG" in str(err)

    def test_role_too_long(self):
        user = User(roles=["x" * 150])
        err = user.verify()
        assert err is not None
        assert "ERROR_ROLE_TOO_LONG" in str(err)

    def test_valid_user_full(self):
        user = User(
            id="1210614a-36ca-4df8-84c6-69f774424d5b",
            first_name="Bob",
            last_name="Smith",
            note="Great guy, that Bob.",
            roles=["test/read"],
        )
        assert user.verify() is None
