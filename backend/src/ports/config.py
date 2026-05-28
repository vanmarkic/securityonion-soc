"""Configstore port — defines the contract for configuration management."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.config import Setting


@runtime_checkable
class Configstore(Protocol):
    """Protocol that any config-storing adapter must satisfy."""

    async def get_settings(self, advanced: bool) -> list[Setting]: ...

    async def update_setting(self, setting: Setting, remove: bool) -> None: ...

    async def sync_settings(self) -> None: ...

    async def sync_module(self, module: str, force: bool) -> None: ...
