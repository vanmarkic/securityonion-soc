"""Node domain model — ported from Go model/node.go."""

from __future__ import annotations

import json
from datetime import UTC, datetime

NODE_ROLE_DESKTOP = "so-desktop"
NODE_STATUS_UNKNOWN = "unknown"
NODE_STATUS_OK = "ok"
NODE_STATUS_FAULT = "fault"
NODE_STATUS_PENDING = "pending"
NODE_STATUS_RESTART = "restart"

# Model -> (image_front, image_back) mapping
_MODEL_IMAGES: dict[str, tuple[str, str]] = {
    "SOSMN": ("sos-1u-front-thumb.jpg", "sos-1u-ethernet-back-thumb.jpg"),
    "SOS500": ("sos-1u-front-thumb.jpg", "sos-1u-ethernet-back-thumb.jpg"),
    "SOS1000": ("sos-1u-front-thumb.jpg", "sos-1u-ethernet-back-thumb.jpg"),
    "SOS1000F": ("sos-1u-front-thumb.jpg", "sos-1u-sfp-back-thumb.jpg"),
    "SOS10K": ("sos-1u-front-thumb.jpg", "sos-1u-sfp-back-thumb.jpg"),
    "SOSSNNV": ("sos-1u-front-thumb.jpg", "sos-1u-sfp-back-thumb.jpg"),
    "SOS4000": ("sos-2u-front-thumb.jpg", "sos-2u-back-thumb.jpg"),
    "SOSSN7200": ("sos-2u-front-thumb.jpg", "sos-2u-back-thumb.jpg"),
    "SO2AMI01": ("so-cloud-aws.jpg", ""),
    "SO2AZI01": ("so-cloud-azure.jpg", ""),
    "SO2GCI01": ("so-cloud-gcp.jpg", ""),
    "SOS500-DE02": ("500v2_front_thumb.jpg", "500v2_back_thumb.jpg"),
    "SOSMN-DE02": ("MNv2_front_thumb.jpg", "MNv2_back_thumb.jpg"),
    "SOS1000-DE02": ("MNv2_front_thumb.jpg", "MNv2_back_thumb.jpg"),
    "SOS2000-DE02": ("MNv2_front_thumb.jpg", "MNv2_back_thumb.jpg"),
    "SOS5000-DE02": ("5000v2_front_thumb.jpg", "5000v2_back_thumb.jpg"),
    "SOSSN7200-DE02": ("5000v2_front_thumb.jpg", "5000v2_back_thumb.jpg"),
    "SOSSNNV-DE02": ("NVv2_front_thumb.jpg", "NVv2_back_thumb.jpg"),
    "SOS10K-DE02": ("NVv2_front_thumb.jpg", "NVv2_back_thumb.jpg"),
    "SOS10KNV-DE02": ("NVv2_front_thumb.jpg", "NVv2_back_thumb.jpg"),
    "SOS-GOFAST-LT-DE02": ("GOFASTv2_front_thumb.jpg", "GOFASTv2_back_thumb.jpg"),
    "SOS-GOFAST-MD-DE02": ("GOFASTv2_front_thumb.jpg", "GOFASTv2_back_thumb.jpg"),
    "SOS-GOFAST-HV-DE02": ("GOFASTv2_front_thumb.jpg", "GOFASTv2_back_thumb.jpg"),
}


class Node:
    def __init__(self, node_id: str) -> None:
        self.id = node_id
        self.online_time: datetime = datetime.now(UTC)
        self.update_time: datetime = datetime.now(UTC)
        self.epoch_time: datetime | None = None
        self.uptime_seconds: int = 0
        self.description: str = ""
        self.mgmt_mac: str = ""
        self.address: str = ""
        self.role: str = ""
        self.model: str = ""
        self.image_front: str = ""
        self.image_back: str = ""
        self.status: str = NODE_STATUS_UNKNOWN
        self.version: str = ""
        self.connection_status: str = NODE_STATUS_UNKNOWN
        self.raid_status: str = NODE_STATUS_UNKNOWN
        self.process_status: str = NODE_STATUS_UNKNOWN
        self.process_json: str = ""
        self.production_eps: int = 0
        self.consumption_eps: int = 0
        self.failed_events: int = 0
        self.eventstore_status: str = NODE_STATUS_UNKNOWN
        self.os_needs_restart: int = 0
        self.os_uptime_seconds: int = 0
        self.metrics_enabled: bool = False
        self.non_critical_node: bool = False
        self.grid_id: str = ""

    def set_model(self, model_name: str) -> None:
        images = _MODEL_IMAGES.get(model_name)
        if images is not None:
            self.model = model_name
            self.image_front = images[0]
            self.image_back = images[1]
        else:
            self.model = "N/A"
            self.image_front = ""
            self.image_back = ""

    def _update_status_component(self, current_state: str, new_state: str) -> str:
        if new_state != NODE_STATUS_UNKNOWN:
            if current_state in (NODE_STATUS_OK, NODE_STATUS_UNKNOWN):
                current_state = new_state
        return current_state

    def update_overall_status(self, enhanced_status_enabled: bool) -> bool:
        self.non_critical_node = self.role == NODE_ROLE_DESKTOP
        new_status = NODE_STATUS_UNKNOWN

        new_status = self._update_status_component(new_status, self.connection_status)

        if enhanced_status_enabled:
            new_status = self._update_status_component(new_status, self.raid_status)
            new_status = self._update_status_component(new_status, self.process_status)
            new_status = self._update_status_component(new_status, self.eventstore_status)

            if self.os_needs_restart == 1 and new_status == NODE_STATUS_OK:
                new_status = NODE_STATUS_RESTART

        # Special case: If process or connection status is unknown then fault
        if (
            (enhanced_status_enabled and self.process_status == NODE_STATUS_UNKNOWN)
            or self.connection_status == NODE_STATUS_UNKNOWN
        ):
            new_status = NODE_STATUS_FAULT

        old_status = self.status
        self.status = new_status
        self.metrics_enabled = enhanced_status_enabled
        return old_status != self.status

    def is_process_running(self, match: str) -> bool:
        if not self.process_json:
            return False
        try:
            data = json.loads(self.process_json)
        except json.JSONDecodeError:
            return False
        containers = data.get("containers", [])
        for proc in containers:
            if proc.get("Name") == match:
                return proc.get("Status") == "running"
        return False

    def is_manager(self) -> bool:
        return self.role in ("so-standalone", "so-manager", "so-eval", "so-import", "so-managersearch")


def new_node(node_id: str) -> Node:
    return Node(node_id)
