"""Tests for the InfoService."""

import json
import os
import tempfile
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


class TestGetCustomReports:
    """Ported from Go server/infohandler_test.go TestInfoHandler_getCustomReports."""

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = InfoService.get_custom_reports(tmpdir)
            assert result == {}

    def test_md_files_with_titles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "report1.md").write_text(
                "Test Report 1\n===============\nContent here"
            )
            Path(tmpdir, "report2.md").write_text(
                "Another Report\n==============\nMore content"
            )
            Path(tmpdir, "not_markdown.txt").write_text(
                "This should be ignored"
            )
            result = InfoService.get_custom_reports(tmpdir)
            assert result == {
                "report1.md": "Test Report 1",
                "report2.md": "Another Report",
            }

    def test_md_file_without_title_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "simple.md").write_text(
                "# Simple Header\nNo underline format"
            )
            result = InfoService.get_custom_reports(tmpdir)
            assert result == {"simple.md": "simple.md"}

    def test_mixed_files_and_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "report.md").write_text(
                "Valid Report\n=============\nContent"
            )
            subdir = Path(tmpdir, "subdir")
            subdir.mkdir()
            Path(subdir, "nested.md").write_text(
                "Should be ignored as it's in subdir"
            )
            result = InfoService.get_custom_reports(tmpdir)
            assert result == {"report.md": "Valid Report"}

    def test_nonexistent_directory(self):
        result = InfoService.get_custom_reports("/nonexistent/path")
        assert result == {}

    def test_good_report_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "good.md").write_text(
                "Good Report\n===========\nContent"
            )
            result = InfoService.get_custom_reports(tmpdir)
            assert result == {"good.md": "Good Report"}


class TestParseReportTitle:
    """Ported from Go server/infohandler_test.go TestInfoHandler_parseReportTitle."""

    def test_valid_title_with_equals_underline(self):
        content = "My Report Title\n===============\nSome content here"
        assert InfoService.parse_report_title(content, "default.md") == "My Report Title"

    def test_multiple_underlines_first_wins(self):
        content = "First Title\n===========\nContent\nSecond Title\n============\nMore content"
        assert InfoService.parse_report_title(content, "default.md") == "First Title"

    def test_no_valid_title_format(self):
        content = "# Header\nSome content\n## Another header"
        assert InfoService.parse_report_title(content, "fallback.md") == "fallback.md"

    def test_empty_content(self):
        assert InfoService.parse_report_title("", "empty.md") == "empty.md"

    def test_only_underline_without_title(self):
        content = "===============\nContent"
        assert InfoService.parse_report_title(content, "noTitle.md") == "noTitle.md"

    def test_title_with_whitespace(self):
        content = "   Trimmed Title   \n===================\nContent"
        assert InfoService.parse_report_title(content, "default.md") == "Trimmed Title"

    def test_underline_too_short(self):
        content = "Title Here\n===\nContent"
        assert InfoService.parse_report_title(content, "short.md") == "Title Here"

    def test_single_line_content(self):
        assert InfoService.parse_report_title("Just one line", "single.md") == "single.md"
