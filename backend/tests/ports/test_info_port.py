"""Tests for the InfoProvider port (Protocol compliance)."""

from src.domain.info import LicenseKey
from src.ports.info import InfoProvider


class FakeInfoProvider:
    """A fake that must satisfy InfoProvider structurally."""

    async def get_version(self) -> str:
        return "2.4.0"

    async def get_elastic_version(self) -> str:
        return "7.17.0"

    async def get_license_info(self) -> tuple[str, str, LicenseKey]:
        lk = LicenseKey(
            effective="",
            expiration="",
            name="",
            id="",
            licensee="",
            features=[],
            users=0,
            nodes=0,
            soc_url="",
            data_url="",
        )
        return "Elastic License 2.0 (ELv2)", "valid", lk

    async def get_timezones(self) -> list[str]:
        return ["UTC", "US/Eastern"]

    async def get_mgmt_mac(self) -> str:
        return "aa:bb:cc:dd:ee:ff"


class TestInfoProvider:
    def test_fake_satisfies_protocol(self):
        """A correctly-shaped fake should be accepted as InfoProvider."""
        provider: InfoProvider = FakeInfoProvider()
        assert isinstance(provider, InfoProvider)

    async def test_get_version(self):
        provider: InfoProvider = FakeInfoProvider()
        version = await provider.get_version()
        assert version == "2.4.0"

    async def test_get_elastic_version(self):
        provider: InfoProvider = FakeInfoProvider()
        ev = await provider.get_elastic_version()
        assert ev == "7.17.0"

    async def test_get_license_info(self):
        provider: InfoProvider = FakeInfoProvider()
        license_text, status, lk = await provider.get_license_info()
        assert license_text == "Elastic License 2.0 (ELv2)"
        assert status == "valid"
        assert isinstance(lk, LicenseKey)

    async def test_get_timezones(self):
        provider: InfoProvider = FakeInfoProvider()
        tzs = await provider.get_timezones()
        assert "UTC" in tzs

    async def test_get_mgmt_mac(self):
        provider: InfoProvider = FakeInfoProvider()
        mac = await provider.get_mgmt_mac()
        assert mac == "aa:bb:cc:dd:ee:ff"
