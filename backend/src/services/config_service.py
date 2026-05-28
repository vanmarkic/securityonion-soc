"""ConfigService — business logic for configuration endpoints."""

from __future__ import annotations

import logging

from src.domain.config import Setting
from src.ports.config import Configstore

logger = logging.getLogger(__name__)


class ConfigService:
    """Service layer for config operations."""

    def __init__(self, configstore: Configstore) -> None:
        self._configstore = configstore

    async def get_settings(self, advanced: bool) -> list[Setting]:
        """Retrieve configuration settings."""
        return await self._configstore.get_settings(advanced)

    async def update_setting(self, setting: Setting, remove: bool) -> None:
        """Update or remove a configuration setting."""
        await self._configstore.update_setting(setting, remove)

    async def sync_settings(self) -> None:
        """Synchronize all settings to the grid."""
        await self._configstore.sync_settings()

    async def sync_module(self, module: str, force: bool) -> None:
        """Synchronize a specific module's state."""
        await self._configstore.sync_module(module, force)
