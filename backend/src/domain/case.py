"""Case domain models — ported from Go model/case.go."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


def _detect_content_type(data: bytes) -> str:
    """Detect MIME type from raw bytes, matching Go's http.DetectContentType behavior.

    Go inspects the first 512 bytes and applies MIME sniffing.
    For plain text content it returns "text/plain; charset=utf-8".
    """
    sniff = data[:512]

    # Check for common binary signatures first
    if sniff[:4] == b"%PDF":
        return "application/pdf"
    if sniff[:2] == b"PK":
        return "application/zip"
    if sniff[:4] == b"\x89PNG":
        return "image/png"
    if sniff[:3] == b"GIF":
        return "image/gif"
    if sniff[:2] in (b"\xff\xd8",):
        return "image/jpeg"

    # If all bytes look like text (matching Go's behavior), return text/plain
    # Go considers bytes text if they are tabs, newlines, or >= 0x20 (space)
    for b in sniff:
        if b <= 0x08 or (0x0E <= b <= 0x1A) or (0x1C <= b <= 0x1F):
            return "application/octet-stream"

    return "text/plain; charset=utf-8"


class Auditable(BaseModel):
    """Base class with audit fields, matching Go's Auditable struct."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    create_time: datetime | None = Field(default=None, alias="createTime")
    update_time: datetime | None = Field(default=None, alias="updateTime")
    user_id: str = Field(default="", alias="userId")
    kind: str = ""
    operation: str = ""


class Case(Auditable):
    """Represents a Security Onion case."""

    start_time: datetime | None = Field(default=None, alias="startTime")
    complete_time: datetime | None = Field(default=None, alias="completeTime")
    title: str = ""
    description: str = ""
    priority: int = 0
    severity: str = ""
    status: str = ""
    template: str = ""
    tlp: str = ""
    pap: str = ""
    category: str = ""
    assignee_id: str = Field(default="", alias="assigneeId")
    tags: list[str] = Field(default_factory=list)

    def process_workflow_for_status(self, old_case: Case) -> None:
        """Update start/complete times based on status transitions."""
        now = datetime.now(UTC)
        if self.status == "closed" and old_case.status != "closed":
            self.complete_time = now
        if old_case.start_time is not None:
            self.start_time = old_case.start_time
        elif self.status == "in progress" and old_case.status != "in progress":
            self.start_time = now


class Comment(Auditable):
    """Represents a case comment."""

    case_id: str = Field(default="", alias="caseId")
    description: str = ""
    hours: float = 0.0


class RelatedEvent(Auditable):
    """Represents a related event attached to a case."""

    case_id: str = Field(default="", alias="caseId")
    fields: dict[str, object] = Field(default_factory=dict)


class Artifact(Auditable):
    """Represents a case artifact (observable)."""

    case_id: str = Field(default="", alias="caseId")
    group_type: str = Field(default="", alias="groupType")
    group_id: str = Field(default="", alias="groupId")
    artifact_type: str = Field(default="", alias="artifactType")
    value: str = ""
    mime_type: str = Field(default="", alias="mimeType")
    stream_len: int = Field(default=0, alias="streamLength")
    stream_id: str = Field(default="", alias="streamId")
    tlp: str = ""
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    ioc: bool = False
    md5: str = ""
    sha1: str = ""
    sha256: str = ""
    protected: bool = False


class ArtifactStream(Auditable):
    """Represents the binary stream of a file artifact."""

    content: str = ""

    def write(self, data: bytes) -> tuple[int, str, str, str, str]:
        """Compute hashes, encode content, detect MIME type.

        Returns (length, mime_type, md5, sha1, sha256).
        """
        self.content = base64.standard_b64encode(data).decode("ascii")
        mime_type = _detect_content_type(data)
        md5 = hashlib.md5(data).hexdigest()
        sha1 = hashlib.sha1(data).hexdigest()
        sha256 = hashlib.sha256(data).hexdigest()
        return len(data), mime_type, md5, sha1, sha256

    def read(self) -> bytes:
        """Decode the base64 content back to raw bytes."""
        return base64.standard_b64decode(self.content)


# Factory functions matching Go's New* constructors

def new_case() -> Case:
    return Case()


def new_related_event() -> RelatedEvent:
    now = datetime.now(UTC)
    return RelatedEvent(create_time=now, fields={})


def new_artifact() -> Artifact:
    now = datetime.now(UTC)
    return Artifact(create_time=now)


def new_artifact_stream() -> ArtifactStream:
    now = datetime.now(UTC)
    return ArtifactStream(create_time=now)


class AttachEventCriteria(BaseModel):
    """Criteria for attaching events to a case (POST /case/events)."""

    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(default="", alias="caseId")
    fields: dict[str, object] = Field(default_factory=dict)
    date_range: str = Field(default="", alias="dateRange")
    date_range_format: str = Field(default="", alias="dateRangeFormat")
    timezone: str = ""
    acknowledged: bool = False
    escalated: bool = False
