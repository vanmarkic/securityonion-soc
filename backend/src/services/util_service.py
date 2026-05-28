"""UtilService — business logic for utility endpoints (DNS reverse lookup)."""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class ReverseLookupProvider(Protocol):
    """Port for performing reverse IP lookups (ES + optional DNS)."""

    async def reverse_lookup(self, ips: list[str], enable_dns: bool) -> dict[str, list[str]]: ...


class UtilService:
    """Service layer for utility operations."""

    def __init__(
        self,
        reverse_lookup_provider: ReverseLookupProvider,
        enable_reverse_lookup: bool = False,
    ) -> None:
        self._provider = reverse_lookup_provider
        self._enable_reverse_lookup = enable_reverse_lookup

    async def reverse_lookup(self, ips: list[str]) -> dict[str, list[str]]:
        """Perform reverse lookup on a list of IP addresses.

        Delegates to the provider, passing the DNS-enabled flag from config.
        """
        return await self._provider.reverse_lookup(ips, self._enable_reverse_lookup)
