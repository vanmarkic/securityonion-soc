"""Playbookstore port — defines the contract for playbook persistence."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.playbook import Playbook


@runtime_checkable
class Playbookstore(Protocol):
    """Protocol that any playbook-storing adapter must satisfy."""

    async def get_playbook_by_id(self, playbook_id: str) -> Playbook | None: ...

    async def get_playbooks_for_detection(
        self, detection_id: str, category: str, engine: str,
    ) -> list[Playbook]: ...

    async def get_event_specific_playbook(
        self, soc_id: str,
    ) -> list[Playbook]: ...
