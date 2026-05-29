"""App configuration — loads sensoroni.json and provides typed config."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


@dataclass(frozen=True)
class AppConfig:
    statickeyauth: StaticKeyAuthConfig = field(default_factory=StaticKeyAuthConfig)
    filedatastore: FileDatastoreConfig = field(default_factory=FileDatastoreConfig)
    staticrbac: StaticRbacConfig = field(default_factory=StaticRbacConfig)
    kratos: KratosConfig = field(default_factory=KratosConfig)

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
        )


def load_config(path: str) -> AppConfig:
    text = Path(path).read_text()
    return AppConfig.from_dict(json.loads(text))
