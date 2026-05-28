"""GridService — business logic for grid endpoints."""

from __future__ import annotations

import copy
import logging

from src.domain.node import Node
from src.domain.status import Status
from src.ports.grid import Datastore, Statusstore

logger = logging.getLogger(__name__)


class GridService:
    """Service layer for grid operations."""

    def __init__(self, datastore: Datastore, statusstore: Statusstore) -> None:
        self._datastore = datastore
        self._statusstore = statusstore

    async def get_status(self, assigned_grid_id: str) -> dict:
        """Get grid status, overriding grid_id with the assigned value.

        Returns a dict copy so the original Status object is not mutated.
        """
        status = await self._statusstore.get_status_summary()
        # Copy to avoid mutating the original object
        status_copy = copy.copy(status)
        status_copy.grid_id = assigned_grid_id
        return _status_to_dict(status_copy)

    async def get_nodes(self, assigned_grid_id: str) -> list[dict]:
        """Get all grid nodes, overriding grid_id with the assigned value.

        Returns copies so the original Node objects are not mutated.
        """
        nodes = await self._datastore.get_nodes()
        result = []
        for node in nodes:
            node_copy = copy.copy(node)
            node_copy.grid_id = assigned_grid_id
            result.append(_node_to_dict(node_copy))
        return result


def _status_to_dict(status: Status) -> dict:
    """Serialize Status to a camelCase dict matching Go JSON output."""
    return {
        "gridId": status.grid_id,
        "grid": {
            "totalNodeCount": status.grid.total_node_count,
            "unhealthyNodeCount": status.grid.unhealthy_node_count,
            "awaitingRebootNodeCount": status.grid.awaiting_reboot_node_count,
            "eps": status.grid.eps,
        },
        "alerts": {
            "newCount": status.alerts.new_count,
        },
        "detections": {
            "elastalert": _engine_to_dict(status.detections.elastalert),
            "suricata": _engine_to_dict(status.detections.suricata),
            "strelka": _engine_to_dict(status.detections.strelka),
        },
    }


def _engine_to_dict(engine) -> dict:
    return {
        "integrityFailure": engine.integrity_failure,
        "migrating": engine.migrating,
        "migrationFailure": engine.migration_failure,
        "importing": engine.importing,
        "syncing": engine.syncing,
        "syncFailure": engine.sync_failure,
        "blocked": engine.blocked,
    }


def _node_to_dict(node: Node) -> dict:
    """Serialize Node to a camelCase dict matching Go JSON output."""
    return {
        "id": node.id,
        "gridId": node.grid_id,
        "description": node.description,
        "address": node.address,
        "role": node.role,
        "model": node.model,
        "imageFront": node.image_front,
        "imageBack": node.image_back,
        "status": node.status,
        "version": node.version,
        "connectionStatus": node.connection_status,
        "raidStatus": node.raid_status,
        "processStatus": node.process_status,
        "productionEps": node.production_eps,
        "consumptionEps": node.consumption_eps,
        "failedEvents": node.failed_events,
        "eventstoreStatus": node.eventstore_status,
        "osNeedsRestart": node.os_needs_restart,
        "osUptimeSeconds": node.os_uptime_seconds,
        "metricsEnabled": node.metrics_enabled,
        "nonCriticalNode": node.non_critical_node,
        "uptimeSeconds": node.uptime_seconds,
    }
