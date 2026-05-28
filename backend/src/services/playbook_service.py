"""PlaybookService — business logic for playbook operations."""

from __future__ import annotations

import logging

import yaml

from src.domain.playbook import Playbook
from src.ports.detections import Detectionstore
from src.ports.playbook import Playbookstore

logger = logging.getLogger(__name__)


class PlaybookService:
    """Business logic for playbook-related endpoints."""

    def __init__(
        self,
        playbookstore: Playbookstore,
        detectionstore: Detectionstore,
    ) -> None:
        self._playbook_store = playbookstore
        self._detection_store = detectionstore

    async def get_playbook(self, playbook_id: str) -> Playbook | None:
        return await self._playbook_store.get_playbook_by_id(playbook_id)

    async def get_playbooks_for_detection(
        self, public_id: str, raw: bool = False,
    ) -> tuple[list[Playbook] | str | None, int]:
        """Get playbooks for a detection, optionally in raw YAML format.

        Returns (result, status_code). Result is either a list of Playbook,
        a raw YAML string, or None (for errors).
        """
        detection = await self._detection_store.get_detection_by_public_id(public_id)
        if detection is None:
            return None, 404

        playbooks = await self._playbook_store.get_playbooks_for_detection(
            public_id, detection.category, detection.engine,
        )
        if not playbooks:
            playbooks = []

        if raw:
            parts = []
            for pb in playbooks:
                raw_output = yaml.dump(
                    pb.model_dump(by_alias=True, exclude_none=True),
                    default_flow_style=False,
                    allow_unicode=True,
                ).strip()
                parts.append(raw_output)
            return "\n---\n".join(parts), 200

        return playbooks, 200

    async def get_event_specific_playbook(
        self, soc_id: str,
    ) -> tuple[list[Playbook] | None, int]:
        """Get playbooks for a specific event.

        Returns (result, status_code).
        """
        try:
            playbooks = await self._playbook_store.get_event_specific_playbook(soc_id)
        except Exception as e:
            if "no alert found" in str(e):
                return None, 404
            raise

        if not playbooks:
            playbooks = []

        return playbooks, 200
