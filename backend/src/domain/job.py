"""Job domain model — ported from Go model/job.go."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

JOB_STATUS_PENDING = 0
JOB_STATUS_COMPLETED = 1
JOB_STATUS_INCOMPLETE = 2
JOB_STATUS_DELETED = 3

DEFAULT_JOB_KIND = "pcap"
JOB_KIND_EXPORT = "reports"


class Job(BaseModel):
    """Represents a job (pcap retrieval, export, analysis, etc.)."""

    model_config = ConfigDict(populate_by_name=True)

    id: int = 0
    create_time: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="createTime")
    status: int = JOB_STATUS_PENDING
    complete_time: datetime = Field(default_factory=lambda: datetime.min.replace(tzinfo=UTC), alias="completeTime")
    fail_time: datetime = Field(default_factory=lambda: datetime.min.replace(tzinfo=UTC), alias="failTime")
    failure: str = ""
    fail_count: int = Field(default=0, alias="failCount")
    owner: str = ""
    node_id: str = Field(default="", alias="nodeId")
    legacy_sensor_id: str = Field(default="", alias="sensorId")
    file_extension: str = Field(default="bin", alias="fileExtension")
    user_id: str = Field(default="", alias="userId")
    kind: str = ""
    size: int = 0

    def get_kind(self) -> str:
        """Return the job kind, defaulting to pcap."""
        if self.kind == "":
            return DEFAULT_JOB_KIND
        return self.kind

    def set_node_id(self, node_id: str) -> None:
        """Set the node id, lowercasing it."""
        self.node_id = node_id.lower()

    def get_node_id(self) -> str:
        """Return the node id (lowercased), falling back to legacy_sensor_id."""
        self.node_id = self.node_id.lower()
        if len(self.node_id) == 0:
            self.legacy_sensor_id = self.legacy_sensor_id.lower()
            return self.legacy_sensor_id
        return self.node_id

    def can_process(self) -> bool:
        """Return True if the job can still be processed."""
        return self.status != JOB_STATUS_COMPLETED and self.status != JOB_STATUS_DELETED

    def complete(self) -> None:
        """Mark the job as completed."""
        self.status = JOB_STATUS_COMPLETED
        self.complete_time = datetime.now(UTC)

    def fail(self, error: str) -> None:
        """Mark the job as incomplete with an error."""
        self.status = JOB_STATUS_INCOMPLETE
        self.failure = error
        self.fail_time = datetime.now(UTC)
        self.fail_count += 1

    def is_eligible_for_retry(self, retry_interval_ms: int, retry_max_attempts: int) -> bool:
        """Return True if the job can be retried."""
        now = datetime.now(UTC)
        retry_time = self.fail_time + timedelta(milliseconds=retry_interval_ms)
        return self.fail_count < retry_max_attempts and retry_time < now


def new_job() -> Job:
    """Factory matching Go's NewJob."""
    return Job()
