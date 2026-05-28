"""Status domain model — ported from Go model/status.go."""

from __future__ import annotations


class EngineState:
    """State of a detection engine (ElastAlert, Suricata, Strelka)."""

    def __init__(self) -> None:
        self.integrity_failure: bool = False
        self.migrating: bool = False
        self.migration_failure: bool = False
        self.importing: bool = False
        self.syncing: bool = False
        self.sync_failure: bool = False
        self.blocked: bool = False

    def is_failure_state(self) -> bool:
        return self.integrity_failure or self.migration_failure or self.sync_failure


class GridStatus:
    def __init__(self) -> None:
        self.total_node_count: int = 0
        self.unhealthy_node_count: int = 0
        self.awaiting_reboot_node_count: int = 0
        self.eps: int = 0


class AlertsStatus:
    def __init__(self) -> None:
        self.new_count: int = 0


class DetectionsStatus:
    def __init__(self) -> None:
        self.elastalert: EngineState = EngineState()
        self.suricata: EngineState = EngineState()
        self.strelka: EngineState = EngineState()


class Status:
    def __init__(self, grid_id: str) -> None:
        self.grid_id: str = grid_id
        self.grid: GridStatus = GridStatus()
        self.alerts: AlertsStatus = AlertsStatus()
        self.detections: DetectionsStatus = DetectionsStatus()


def new_status(grid_id: str) -> Status:
    return Status(grid_id)
