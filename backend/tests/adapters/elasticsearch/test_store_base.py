from unittest.mock import AsyncMock

from src.adapters.elasticsearch.converter import convert_object_to_document_map
from src.adapters.elasticsearch.store_base import (
    delete_document,
    delete_with_audit,
    index_document,
    save_with_audit,
)


def test_convert_object_to_document_map() -> None:
    doc = convert_object_to_document_map("test", {"a": 1}, "so_")
    assert doc["so_test"] == {"a": 1}
    assert "@timestamp" in doc


async def test_index_document_refresh_true() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "x1", "result": "created"}
    r = await index_document(es, "*:so-case", {"so_kind": "case"}, "abc12")
    assert r.document_id == "x1" and r.success is True
    kwargs = es.index.await_args.kwargs
    assert kwargs["refresh"] == "true"
    assert kwargs["index"] == "so-case"  # cross-cluster prefix stripped on write
    assert kwargs["id"] == "abc12"


async def test_index_document_empty_id_omitted() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "auto1", "result": "created"}
    r = await index_document(es, "*:so-case", {"so_kind": "case"}, "")
    assert r.document_id == "auto1"
    kwargs = es.index.await_args.kwargs
    # Empty id -> auto-generated; "id" must not be passed to ES.
    assert "id" not in kwargs
    assert kwargs["refresh"] == "true"


async def test_save_with_audit_writes_two_docs() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "live1", "result": "created"}
    result = await save_with_audit(
        es,
        index="*:so-case",
        audit_index="*:so-casehistory",
        document={"so_kind": "case"},
        doc_id="",
        prefix="so_",
    )
    assert result.document_id == "live1"
    assert es.index.await_count == 2
    # second call -> audit index with operation=create and audit_doc_id=live1
    audit_kwargs = es.index.await_args_list[1].kwargs
    assert audit_kwargs["index"] == "so-casehistory"
    assert audit_kwargs["document"]["so_operation"] == "create"
    assert audit_kwargs["document"]["so_audit_doc_id"] == "live1"
    # audit doc indexed with auto id (no id kwarg)
    assert "id" not in audit_kwargs


async def test_save_with_audit_update_operation() -> None:
    es = AsyncMock()
    es.index.return_value = {"_id": "live1", "result": "updated"}
    await save_with_audit(
        es,
        index="*:so-case",
        audit_index="*:so-casehistory",
        document={"so_kind": "case"},
        doc_id="abc12",  # non-empty -> update
        prefix="so_",
    )
    audit_kwargs = es.index.await_args_list[1].kwargs
    assert audit_kwargs["document"]["so_operation"] == "update"


async def test_save_with_audit_swallows_audit_failure() -> None:
    es = AsyncMock()
    # First call (live) succeeds; second call (audit) raises.
    es.index.side_effect = [
        {"_id": "live1", "result": "created"},
        RuntimeError("audit index down"),
    ]
    # Audit failure is logged, not raised; live result still returned.
    result = await save_with_audit(
        es,
        index="*:so-case",
        audit_index="*:so-casehistory",
        document={"so_kind": "case"},
        doc_id="",
        prefix="so_",
    )
    assert result.document_id == "live1" and result.success is True


async def test_delete_document_strips_prefix() -> None:
    es = AsyncMock()
    es.delete.return_value = {"_id": "abc12", "result": "deleted"}
    await delete_document(es, "*:so-case", "abc12")
    kwargs = es.delete.await_args.kwargs
    assert kwargs["index"] == "so-case"
    assert kwargs["id"] == "abc12"


async def test_delete_with_audit_writes_audit_delete_doc() -> None:
    es = AsyncMock()
    es.delete.return_value = {"_id": "abc12", "result": "deleted"}
    es.index.return_value = {"_id": "audit1", "result": "created"}
    await delete_with_audit(
        es,
        index="*:so-case",
        audit_index="*:so-casehistory",
        document={"so_kind": "case"},
        doc_id="abc12",
        prefix="so_",
    )
    es.delete.assert_awaited_once()
    es.index.assert_awaited_once()
    audit_kwargs = es.index.await_args.kwargs
    assert audit_kwargs["index"] == "so-casehistory"
    assert audit_kwargs["document"]["so_operation"] == "delete"
    assert audit_kwargs["document"]["so_audit_doc_id"] == "abc12"
    assert audit_kwargs["document"]["so_kind"] == "case"
