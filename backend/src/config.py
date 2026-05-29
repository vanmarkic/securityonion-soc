"""App configuration — loads sensoroni.json and provides typed config."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.adapters.elasticsearch.config import ElasticConfig


@dataclass(frozen=True)
class StaticKeyAuthConfig:
    api_key: str = ""
    anonymous_cidr: str = "0.0.0.0/0"


@dataclass(frozen=True)
class FileDatastoreConfig:
    job_dir: str = "jobs"
    retry_failure_interval_ms: int = 600_000
    retry_failure_max_attempts: int = 5


@dataclass(frozen=True)
class StaticRbacConfig:
    role_files: list[str] = field(default_factory=list)
    user_files: list[str] = field(default_factory=list)
    scan_interval_ms: int = 60_000
    default_role: str = ""


@dataclass(frozen=True)
class KratosConfig:
    host_url: str = ""


# Maps the sensoroni ``elastic`` module's camelCase JSON keys to the snake_case
# fields of ``ElasticConfig`` (see server/modules/elastic/elastic.go). Only keys
# present in the JSON are forwarded; everything else falls back to the
# ``ElasticConfig`` pydantic defaults.
_ELASTIC_KEY_MAP: dict[str, str] = {
    "hostUrl": "host_url",
    "remoteHostUrls": "remote_host_urls",
    "extractCommonObservables": "extract_common_observables",
    "verifyCert": "verify_cert",
    "username": "username",
    "password": "password",
    "timeShiftMs": "time_shift_ms",
    "defaultDurationMs": "default_duration_ms",
    "esSearchOffsetMs": "es_search_offset_ms",
    "timeoutMs": "timeout_ms",
    "cacheMs": "cache_ms",
    "index": "index",
    "asyncThreshold": "async_threshold",
    "intervals": "intervals",
    "maxLogLength": "max_log_length",
    "casesEnabled": "cases_enabled",
    "lookupTunnelParent": "lookup_tunnel_parent",
    "detectionsEnabled": "detections_enabled",
    "assistantEnabled": "assistant_enabled",
    "maxScrollSize": "max_scroll_size",
    "caseIndex": "case_index",
    "auditIndex": "audit_index",
    "maxCaseAssociations": "max_case_associations",
    "schemaPrefix": "schema_prefix",
    "detectionIndex": "detection_index",
    "detectionAuditIndex": "detection_audit_index",
    "maxDetectionAssociations": "max_detection_associations",
    "assistantChatIndex": "assistant_chat_index",
    "assistantSessionIndex": "assistant_session_index",
    "bulkIndexerWorkerCount": "bulk_indexer_worker_count",
}


def _parse_elastic(modules: dict[str, Any]) -> ElasticConfig | None:
    """Build an ElasticConfig from the ``elastic``/``elasticsearch`` module block.

    Returns ``None`` when neither block is present so wiring can stay
    absent-safe (default ``create_app`` leaves the ES routes unwired).
    """
    raw = modules.get("elastic")
    if raw is None:
        raw = modules.get("elasticsearch")
    if raw is None:
        return None
    kwargs = {
        snake: raw[camel] for camel, snake in _ELASTIC_KEY_MAP.items() if camel in raw
    }
    return ElasticConfig(**kwargs)


@dataclass(frozen=True)
class AppConfig:
    statickeyauth: StaticKeyAuthConfig = field(default_factory=StaticKeyAuthConfig)
    filedatastore: FileDatastoreConfig = field(default_factory=FileDatastoreConfig)
    staticrbac: StaticRbacConfig = field(default_factory=StaticRbacConfig)
    kratos: KratosConfig = field(default_factory=KratosConfig)
    elasticsearch: ElasticConfig | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        modules = raw.get("server", {}).get("modules", {})

        ska = modules.get("statickeyauth", {})
        fds = modules.get("filedatastore", {})
        rbac = modules.get("staticrbac", {})
        kra = modules.get("kratos", {})

        return cls(
            statickeyauth=StaticKeyAuthConfig(
                api_key=ska.get("apiKey", ""),
                anonymous_cidr=ska.get("anonymousCidr", "0.0.0.0/0"),
            ),
            filedatastore=FileDatastoreConfig(
                job_dir=fds.get("jobDir", "jobs"),
                retry_failure_interval_ms=fds.get("retryFailureIntervalMs", 600_000),
                retry_failure_max_attempts=fds.get("retryFailureMaxAttempts", 5),
            ),
            staticrbac=StaticRbacConfig(
                role_files=rbac.get("roleFiles", []),
                user_files=rbac.get("userFiles", []),
                scan_interval_ms=rbac.get("scanIntervalMs", 60_000),
                default_role=rbac.get("defaultRole", ""),
            ),
            kratos=KratosConfig(
                host_url=kra.get("hostUrl", ""),
            ),
            elasticsearch=_parse_elastic(modules),
        )


def load_config(path: str) -> AppConfig:
    text = Path(path).read_text()
    return AppConfig.from_dict(json.loads(text))
