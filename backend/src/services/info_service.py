"""InfoService — assembles the Info response from ports."""

from __future__ import annotations

from src.domain.info import Info
from src.ports.info import InfoProvider
from src.ports.users import Userstore


class InfoService:
    """Business logic for the /api/info/ endpoint."""

    def __init__(self, info_provider: InfoProvider, userstore: Userstore) -> None:
        self._info_provider = info_provider
        self._userstore = userstore

    async def get_info(self, user_id: str) -> Info:
        """Assemble the full Info response for the given user."""
        version = await self._info_provider.get_version()
        elastic_version = await self._info_provider.get_elastic_version()
        license_text, license_status, license_key = await self._info_provider.get_license_info()
        timezones = await self._info_provider.get_timezones()
        mgmt_mac = await self._info_provider.get_mgmt_mac()

        user = await self._userstore.get_user_by_id(user_id)
        force_otp = False
        if user is not None:
            force_otp = user.totp_status == "forced"

        return Info(
            version=version,
            license=license_text,
            parameters=None,
            elastic_version=elastic_version,
            user_id=user_id,
            timezones=timezones,
            srv_token="",
            license_key=license_key,
            license_status=license_status,
            force_user_otp=force_otp,
            mgmt_mac=mgmt_mac,
            custom_reports={},
            subgrids=[],
        )
