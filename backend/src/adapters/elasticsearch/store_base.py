"""Shared store base — index/delete + audit dual-write.

Factors the document-store mechanics shared by the case, detection, and
assistant stores (Go ``elasticcasestore.go`` ``save``/``delete``,
``elasticeventstore.go`` ``Index``/``Delete``):

- index a ``{<prefix><kind>: obj, '@timestamp': now}`` document with
  ``refresh="true"`` (read-after-write), and
- write an audit snapshot of the same document into the history index,
  tagged with ``<prefix>audit_doc_id`` and ``<prefix>operation``
  (``create`` / ``update`` / ``delete``).

The live write strips the cross-cluster prefix from the index (Go
``disableCrossClusterIndex``) and resolves ``{today}`` (Go ``transformIndex``);
the audit write follows the same rules. An empty ``doc_id`` lets Elasticsearch
auto-generate the id (the ``id`` kwarg is omitted rather than passed empty).

Divergence from Go: the Python case/detection/assistant ports take no ``ctx``
and perform no ``server.CheckAuthorized`` — authorization happens at the
FastAPI route/dependency layer — so Go's ``CheckAuthorized("write", ...)``
calls are dropped here. The audit write failure is logged (not raised), exactly
as Go does, so a successful live write is never masked by an audit-index error.
"""

from __future__ import annotations

import logging
from typing import Any

from elasticsearch import AsyncElasticsearch

from src.adapters.elasticsearch.converter import IndexResult, parse_index_results
from src.adapters.elasticsearch.helpers import (
    AUDIT_DOC_ID,
    disable_cross_cluster_index,
    transform_index,
)

logger = logging.getLogger(__name__)


def _write_index(index: str) -> str:
    """Resolve an index for a write: strip cross-cluster prefix, expand {today}."""
    return transform_index(disable_cross_cluster_index(index))


async def index_document(
    es: AsyncElasticsearch,
    index: str,
    document: dict[str, Any],
    doc_id: str,
) -> IndexResult:
    """Index a document with ``refresh="true"`` (Go ``indexDocument``).

    The cross-cluster prefix is stripped and ``{today}`` resolved before the
    write. An empty ``doc_id`` is omitted so Elasticsearch auto-generates one.
    """
    kwargs: dict[str, Any] = {
        "index": _write_index(index),
        "document": document,
        "refresh": "true",
    }
    if doc_id:
        kwargs["id"] = doc_id
    resp = await es.index(**kwargs)
    return parse_index_results(dict(resp))


async def delete_document(
    es: AsyncElasticsearch,
    index: str,
    doc_id: str,
) -> IndexResult:
    """Delete a document by id (Go ``deleteDocument``)."""
    resp = await es.delete(index=_write_index(index), id=doc_id)
    return parse_index_results(dict(resp))


async def save_with_audit(
    es: AsyncElasticsearch,
    *,
    index: str,
    audit_index: str,
    document: dict[str, Any],
    doc_id: str,
    prefix: str,
    operation: str | None = None,
) -> IndexResult:
    """Index a live document, then write an audit snapshot (Go ``save``).

    ``operation`` is ``create`` when ``doc_id`` is empty, otherwise ``update``,
    unless an explicit ``operation`` override is supplied (Go's
    ``modcontext.WriteOverrideOperation`` — the detection create path forces
    ``create`` even though the document is indexed with a deterministic id). The
    audit document carries ``<prefix>audit_doc_id`` set to the live document's id
    and is indexed with an auto-generated id. An audit-write failure is logged,
    not raised.
    """
    result = await index_document(es, index, document, doc_id)

    document[prefix + AUDIT_DOC_ID] = result.document_id
    if operation is not None:
        document[prefix + "operation"] = operation
    else:
        document[prefix + "operation"] = "create" if doc_id == "" else "update"
    try:
        await index_document(es, audit_index, document, "")
    except Exception:  # noqa: BLE001 — audit failure must not mask the live write
        logger.exception(
            "Object indexed successfully however audit record failed to index "
            "(documentId=%s)",
            result.document_id,
        )
    return result


async def delete_with_audit(
    es: AsyncElasticsearch,
    *,
    index: str,
    audit_index: str,
    document: dict[str, Any],
    doc_id: str,
    prefix: str,
) -> None:
    """Delete a live document, then write a ``delete`` audit snapshot (Go ``delete``).

    The audit document carries ``<prefix>audit_doc_id`` set to the deleted id
    and ``<prefix>operation = "delete"``. An audit-write failure is logged,
    not raised.
    """
    await delete_document(es, index, doc_id)

    document[prefix + AUDIT_DOC_ID] = doc_id
    document[prefix + "operation"] = "delete"
    try:
        await index_document(es, audit_index, document, "")
    except Exception:  # noqa: BLE001 — audit failure must not mask the live delete
        logger.exception(
            "Object deleted successfully however audit record failed to index "
            "(documentId=%s)",
            doc_id,
        )
