"""Tests for the InfoService."""

import json
from pathlib import Path

from src.domain.info import Info, LicenseKey
from src.domain.user import User
from src.services.info_service import InfoService


GOLDEN_MASTER = Path(__file__).parent.parent / "characterization" / "golden_masters" / "get_api_info.json"


class FakeInfoProvider:
    async def get_version(self) -> str:
        return "unknown"

    async def get_elastic_version(self) -> str:
        return ""

    async def get_license_info(self) -> tuple[str, str, LicenseKey]:
        lk = LicenseKey(
            effective="0001-01-01T00:00:00Z",
            expiration="0001-01-01T00:00:00Z",
            name="",
            id="",
            licensee="",
            features=["api", "fps"],
            users=0,
            nodes=0,
            soc_url="",
            data_url="",
        )
        return "Elastic License 2.0 (ELv2)", "invalid", lk

    async def get_timezones(self) -> list[str]:
        return ["UTC", "US/Eastern"]

    async def get_mgmt_mac(self) -> str:
        return "unknown"


class FakeUserstore:
    def __init__(self, users: list[User] | None = None):
        self._users = users if users is not None else [
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
            ),
        ]

    async def get_users(self) -> list[User]:
        return self._users

    async def get_user_by_id(self, user_id: str) -> User | None:
        for u in self._users:
            if u.id == user_id:
                return u
        return None


class TestInfoService:
    async def test_get_info_returns_info_model(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert isinstance(result, Info)

    async def test_get_info_populates_version(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.version == "unknown"

    async def test_get_info_populates_user_id(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.user_id == "user-1"

    async def test_get_info_populates_license(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.license == "Elastic License 2.0 (ELv2)"
        assert result.license_status == "invalid"
        assert result.license_key.features == ["api", "fps"]

    async def test_get_info_populates_timezones(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.timezones == ["UTC", "US/Eastern"]

    async def test_get_info_populates_elastic_version(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.elastic_version == ""

    async def test_get_info_populates_mgmt_mac(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.mgmt_mac == "unknown"

    async def test_get_info_default_values(self):
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.parameters is None
        assert result.srv_token == ""
        assert result.force_user_otp is False
        assert result.custom_reports == {}
        assert result.subgrids == []

    async def test_get_info_output_matches_golden_master_keys(self):
        """The serialized output must have the same top-level keys as the golden master."""
        golden = json.loads(GOLDEN_MASTER.read_text())
        expected_keys = set(golden["response_body"].keys())

        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        actual_keys = set(result.model_dump(by_alias=True).keys())
        assert actual_keys == expected_keys

    async def test_force_user_otp_when_totp_forced(self):
        """force_user_otp should be True when the user's totp_status is 'forced'."""
        forced_user = User(
            id="user-forced",
            email="forced@example.com",
            first_name="Forced",
            last_name="User",
            note="",
            roles=["analyst"],
            status="active",
            totp_status="forced",
            webauthn_status="disabled",
        )
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(users=[forced_user]),
        )
        result = await service.get_info(user_id="user-forced")
        assert result.force_user_otp is True

    async def test_force_user_otp_false_when_totp_disabled(self):
        """force_user_otp should be False when the user's totp_status is not 'forced'."""
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="user-1")
        assert result.force_user_otp is False

    async def test_force_user_otp_false_when_user_not_found(self):
        """force_user_otp should be False when the user is not in the userstore."""
        service = InfoService(
            info_provider=FakeInfoProvider(),
            userstore=FakeUserstore(),
        )
        result = await service.get_info(user_id="nonexistent")
        assert result.force_user_otp is False
