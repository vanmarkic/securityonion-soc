"""Shared fixtures + skip guard for ES integration tests.

These tests require a live single-node Elasticsearch. Bring one up with:

    docker compose -f docker-compose.dev.yml up -d

then run:

    .venv/bin/python -m pytest tests/adapters/elasticsearch/integration -v

When no ES is reachable on ``ES_TEST_URL`` (default http://localhost:9200)
every test in this package is SKIPPED, so the default suite stays green
without Docker.
"""

from __future__ import annotations

import os
import socket
import urllib.parse
from collections.abc import AsyncIterator

import pytest
from elasticsearch import AsyncElasticsearch

ES_URL = os.environ.get("ES_TEST_URL", "http://localhost:9200")


def es_available() -> bool:
    """Cheap TCP probe so the suite skips fast when ES is absent."""
    u = urllib.parse.urlparse(ES_URL)
    try:
        with socket.create_connection((u.hostname, u.port or 9200), timeout=0.5):
            return True
    except OSError:
        return False


# Applied package-wide via conftest: pytest collects this and the per-module
# pytestmark stacks with it.
collect_ignore_glob: list[str] = []


@pytest.fixture
async def real_es() -> AsyncIterator[AsyncElasticsearch]:
    es = AsyncElasticsearch(hosts=[ES_URL], verify_certs=False, ssl_show_warn=False)
    try:
        yield es
    finally:
        await es.close()
