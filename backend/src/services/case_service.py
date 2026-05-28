"""CaseService — business logic for case operations."""

from __future__ import annotations

import logging
from typing import Any

from src.domain.case import (
    Artifact,
    ArtifactStream,
    Case,
    Comment,
    RelatedEvent,
)
from src.ports.cases import Casestore

logger = logging.getLogger(__name__)


class CaseService:
    """Business logic for all case-related endpoints."""

    def __init__(self, casestore: Casestore) -> None:
        self._store = casestore

    # -- Case CRUD --

    async def create_case(self, case: Case) -> Case:
        return await self._store.create(case)

    async def update_case(self, case: Case) -> Case:
        return await self._store.update(case)

    async def get_case(self, case_id: str) -> Case | None:
        return await self._store.get_case(case_id)

    async def get_case_history(self, case_id: str) -> list[Any]:
        return await self._store.get_case_history(case_id)

    # -- Comment CRUD --

    async def create_comment(self, comment: Comment) -> Comment:
        return await self._store.create_comment(comment)

    async def get_comments(self, case_id: str) -> list[Comment]:
        return await self._store.get_comments(case_id)

    async def update_comment(self, comment: Comment) -> Comment:
        return await self._store.update_comment(comment)

    async def delete_comment(self, comment_id: str) -> None:
        await self._store.delete_comment(comment_id)

    # -- Related Events --

    async def get_related_events(self, case_id: str) -> list[RelatedEvent]:
        return await self._store.get_related_events(case_id)

    async def delete_related_event(self, event_id: str) -> None:
        await self._store.delete_related_event(event_id)

    async def create_related_events(
        self, events: list[RelatedEvent],
    ) -> tuple[int, dict[str, str], None | str]:
        return await self._store.create_related_events(events)

    # -- Artifact CRUD --

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        return await self._store.create_artifact(artifact)

    async def get_artifacts(
        self, case_id: str, group_type: str, group_id: str,
    ) -> list[Artifact]:
        return await self._store.get_artifacts(case_id, group_type, group_id)

    async def update_artifact(self, artifact: Artifact) -> Artifact:
        return await self._store.update_artifact(artifact)

    async def delete_artifact(self, artifact_id: str) -> None:
        await self._store.delete_artifact(artifact_id)

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        return await self._store.get_artifact(artifact_id)

    async def get_artifact_stream(self, stream_id: str) -> ArtifactStream | None:
        return await self._store.get_artifact_stream(stream_id)

    async def create_artifact_stream(self, stream: ArtifactStream) -> str:
        return await self._store.create_artifact_stream(stream)
