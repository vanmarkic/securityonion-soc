from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from elasticsearch import AsyncElasticsearch


def build_async_client(
    host: str, user: str, password: str, *, verify_cert: bool, timeout_ms: int
) -> AsyncElasticsearch:
    kwargs: dict[str, Any] = {
        "verify_certs": verify_cert,  # Go: InsecureSkipVerify = !verify_cert
        "ssl_show_warn": False,
        "request_timeout": timeout_ms / 1000.0,
    }
    if user and password:
        kwargs["basic_auth"] = (user, password)
    return AsyncElasticsearch(hosts=[host], **kwargs)


@dataclass
class ElasticClients:
    primary: AsyncElasticsearch
    remotes: list[AsyncElasticsearch] = field(default_factory=list)

    @property
    def read_client(self) -> AsyncElasticsearch:
        return self.primary

    @property
    def all_clients(self) -> list[AsyncElasticsearch]:
        return [self.primary, *self.remotes]
