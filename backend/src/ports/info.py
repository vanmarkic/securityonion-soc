"""InfoProvider port — defines the contract for fetching system info."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from src.domain.info import LicenseKey


@runtime_checkable
class InfoProvider(Protocol):
    """Protocol that any info-providing adapter must satisfy."""

    async def get_version(self) -> str: ...

    async def get_elastic_version(self) -> str: ...

    async def get_license_info(self) -> tuple[str, str, LicenseKey]: ...

    async def get_timezones(self) -> list[str]: ...

    async def get_mgmt_mac(self) -> str: ...

    async def get_parameters(self) -> dict[str, Any]: ...
