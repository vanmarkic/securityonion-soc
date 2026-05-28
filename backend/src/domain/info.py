"""Info domain model — represents the /api/info/ response shape."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LicenseKey(BaseModel):
    """License key details embedded within the Info response."""

    model_config = ConfigDict(populate_by_name=True)

    effective: str
    expiration: str
    name: str
    id: str
    licensee: str
    features: list[str]
    users: int
    nodes: int
    soc_url: str = Field(alias="socUrl")
    data_url: str = Field(alias="dataUrl")


class Info(BaseModel):
    """Top-level info response returned by GET /api/info/."""

    model_config = ConfigDict(populate_by_name=True)

    version: str
    license: str
    parameters: dict[str, Any] | None
    elastic_version: str = Field(alias="elasticVersion")
    user_id: str = Field(alias="userId")
    timezones: list[str]
    srv_token: str = Field(alias="srvToken")
    license_key: LicenseKey = Field(alias="licenseKey")
    license_status: str = Field(alias="licenseStatus")
    force_user_otp: bool = Field(alias="forceUserOtp")
    mgmt_mac: str = Field(alias="mgmtMac")
    custom_reports: dict[str, Any] = Field(alias="customReports")
    subgrids: list[Any] = Field(alias="subgrids")
