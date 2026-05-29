"""Tests for the Info domain model."""

import json
from pathlib import Path

from src.domain.info import Info, LicenseKey

GOLDEN_MASTER = Path(__file__).parent.parent / "characterization" / "golden_masters" / "get_api_info.json"


class TestLicenseKey:
    def test_create_license_key(self):
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
        assert lk.effective == "0001-01-01T00:00:00Z"
        assert lk.features == ["api", "fps"]

    def test_license_key_camel_case_serialization(self):
        lk = LicenseKey(
            effective="0001-01-01T00:00:00Z",
            expiration="0001-01-01T00:00:00Z",
            name="",
            id="",
            licensee="",
            features=[],
            users=0,
            nodes=0,
            soc_url="https://example.com",
            data_url="https://data.example.com",
        )
        data = lk.model_dump(by_alias=True)
        assert "socUrl" in data
        assert "dataUrl" in data
        assert "soc_url" not in data
        assert "data_url" not in data


class TestInfo:
    def test_create_info(self):
        info = Info(
            version="unknown",
            license="Elastic License 2.0 (ELv2)",
            parameters=None,
            elastic_version="",
            user_id="00000000-0000-0000-0000-000000000001",
            timezones=["UTC"],
            srv_token="",
            license_key=LicenseKey(
                effective="0001-01-01T00:00:00Z",
                expiration="0001-01-01T00:00:00Z",
                name="",
                id="",
                licensee="",
                features=[],
                users=0,
                nodes=0,
                soc_url="",
                data_url="",
            ),
            license_status="invalid",
            force_user_otp=False,
            mgmt_mac="unknown",
            custom_reports={},
            subgrids=[],
        )
        assert info.version == "unknown"
        assert info.user_id == "00000000-0000-0000-0000-000000000001"

    def test_info_camel_case_serialization(self):
        info = Info(
            version="unknown",
            license="Elastic License 2.0 (ELv2)",
            parameters=None,
            elastic_version="7.17.0",
            user_id="user-1",
            timezones=["UTC"],
            srv_token="tok",
            license_key=LicenseKey(
                effective="0001-01-01T00:00:00Z",
                expiration="0001-01-01T00:00:00Z",
                name="",
                id="",
                licensee="",
                features=[],
                users=0,
                nodes=0,
                soc_url="",
                data_url="",
            ),
            license_status="invalid",
            force_user_otp=False,
            mgmt_mac="unknown",
            custom_reports={},
            subgrids=[],
        )
        data = info.model_dump(by_alias=True)
        assert "elasticVersion" in data
        assert "userId" in data
        assert "srvToken" in data
        assert "licenseKey" in data
        assert "licenseStatus" in data
        assert "forceUserOtp" in data
        assert "mgmtMac" in data
        assert "customReports" in data
        # snake_case should NOT be in alias dump
        assert "elastic_version" not in data
        assert "user_id" not in data

    def test_info_matches_golden_master_shape(self):
        """The model must produce the exact same keys as the golden master response_body."""
        golden = json.loads(GOLDEN_MASTER.read_text())
        expected_keys = set(golden["response_body"].keys())

        info = Info(
            version="unknown",
            license="Elastic License 2.0 (ELv2)",
            parameters=None,
            elastic_version="",
            user_id="00000000-0000-0000-0000-000000000001",
            timezones=["UTC"],
            srv_token="",
            license_key=LicenseKey(
                effective="0001-01-01T00:00:00Z",
                expiration="0001-01-01T00:00:00Z",
                name="",
                id="",
                licensee="",
                features=[],
                users=0,
                nodes=0,
                soc_url="",
                data_url="",
            ),
            license_status="invalid",
            force_user_otp=False,
            mgmt_mac="unknown",
            custom_reports={},
            subgrids=[],
        )
        actual_keys = set(info.model_dump(by_alias=True).keys())
        assert actual_keys == expected_keys

    def test_info_populate_by_name(self):
        """Can construct using either snake_case or camelCase field names."""
        info = Info(
            version="v1",
            license="MIT",
            parameters=None,
            elasticVersion="7.0",
            userId="u1",
            timezones=[],
            srvToken="",
            licenseKey=LicenseKey(
                effective="",
                expiration="",
                name="",
                id="",
                licensee="",
                features=[],
                users=0,
                nodes=0,
                socUrl="",
                dataUrl="",
            ),
            licenseStatus="valid",
            forceUserOtp=True,
            mgmtMac="aa:bb",
            customReports={},
            subgrids=[],
        )
        assert info.elastic_version == "7.0"
        assert info.user_id == "u1"
        assert info.force_user_otp is True
