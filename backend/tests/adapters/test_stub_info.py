"""Tests for the stub InfoProvider and Userstore adapters."""

from src.adapters.stub.info_provider import StubInfoProvider
from src.adapters.stub.userstore import StubUserstore
from src.domain.info import LicenseKey
from src.domain.user import User
from src.ports.info import InfoProvider
from src.ports.users import Userstore


class TestStubInfoProvider:
    def test_satisfies_protocol(self):
        provider: InfoProvider = StubInfoProvider()
        assert isinstance(provider, InfoProvider)

    async def test_get_version(self):
        provider = StubInfoProvider()
        version = await provider.get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    async def test_get_elastic_version(self):
        provider = StubInfoProvider()
        ev = await provider.get_elastic_version()
        assert isinstance(ev, str)

    async def test_get_license_info(self):
        provider = StubInfoProvider()
        license_text, status, lk = await provider.get_license_info()
        assert isinstance(license_text, str)
        assert isinstance(status, str)
        assert isinstance(lk, LicenseKey)
        assert isinstance(lk.features, list)

    async def test_get_timezones(self):
        provider = StubInfoProvider()
        tzs = await provider.get_timezones()
        assert isinstance(tzs, list)
        assert len(tzs) > 0
        assert "UTC" in tzs

    async def test_get_mgmt_mac(self):
        provider = StubInfoProvider()
        mac = await provider.get_mgmt_mac()
        assert isinstance(mac, str)

    async def test_get_parameters_is_non_null_with_client_fields(self):
        provider = StubInfoProvider()
        params = await provider.get_parameters()
        # Must be a non-null object — the frontend binds parameters.docsUrl etc.
        assert isinstance(params, dict)
        for key in ("docsUrl", "cheatsheetUrl", "releaseNotesUrl"):
            assert isinstance(params[key], str) and params[key]
        assert isinstance(params["inactiveTools"], list)
        assert isinstance(params["tools"], list)


class TestStubUserstore:
    def test_satisfies_protocol(self):
        store: Userstore = StubUserstore()
        assert isinstance(store, Userstore)

    async def test_get_users(self):
        store = StubUserstore()
        users = await store.get_users()
        assert isinstance(users, list)
        assert len(users) > 0
        assert all(isinstance(u, User) for u in users)

    async def test_get_user_by_id_found(self):
        store = StubUserstore()
        users = await store.get_users()
        first_id = users[0].id
        user = await store.get_user_by_id(first_id)
        assert user is not None
        assert user.id == first_id

    async def test_get_user_by_id_not_found(self):
        store = StubUserstore()
        user = await store.get_user_by_id("nonexistent-id")
        assert user is None
