"""InfoService — assembles the Info response from ports."""

from __future__ import annotations

import logging
import os

from src.domain.info import Info
from src.ports.info import InfoProvider
from src.ports.users import Userstore

logger = logging.getLogger(__name__)


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

    @staticmethod
    def get_custom_reports(path: str) -> dict[str, str]:
        """Scan a directory for .md files and extract titles.

        Ported from Go server/infohandler.go getCustomReports.
        """
        reports: dict[str, str] = {}
        try:
            entries = os.listdir(path)
        except OSError:
            logger.error("Failed to read custom reports directory: %s", path)
            return reports

        for name in entries:
            full_path = os.path.join(path, name)
            if os.path.isdir(full_path):
                continue
            if not name.endswith(".md"):
                continue
            try:
                with open(full_path) as f:
                    content = f.read()
            except OSError:
                logger.error("Failed to read custom report file: %s", full_path)
                continue
            title = InfoService.parse_report_title(content, name)
            reports[name] = title

        return reports

    @staticmethod
    def parse_report_title(content: str, default: str) -> str:
        """Extract title from rst-style underline format, falling back to default.

        Ported from Go server/infohandler.go parseReportTitle.
        Looks for a line followed by a line starting with "===".
        """
        prev_line = ""
        for line in content.split("\n"):
            stripped = line.strip()
            if line.startswith("===") and prev_line != "":
                return prev_line
            prev_line = stripped
        return default
