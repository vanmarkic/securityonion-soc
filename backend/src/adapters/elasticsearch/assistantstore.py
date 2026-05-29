"""ElasticAssistantstore — ES-backed implementation of the Assistantstore port.

Ports ``server/modules/elastic/elasticassistantstore.go`` (``validateId``,
``validateChat``, ``validateSession``, ``prepareForSave``, ``save``,
``SaveChat``, ``GetChatHistory``, ``GetSessions`` + ``addMetaFromMessages``,
``CreateSession``, ``UpdateSessionTags``, ``DeleteSession``).

Unlike the case/detection stores, the assistant store does not read back through
a composed eventstore: Go parses session/chat hits directly from
``_source[<prefix>session]`` / ``_source[<prefix>chat]`` with a hand-built ES
query (term filters + ``must_not exists deleteTime`` + ``@timestamp`` range, sort
``@timestamp`` asc, size 10000). This adapter mirrors that exactly, calling the
async ES client's ``search`` / ``msearch`` / ``update_by_query`` directly.

Storage shape (Go ``saveableMessage`` / ``StoredMessage.MarshalJSON``): a chat is
stored under ``<prefix>chat`` with the message flattened to camelCase storage
keys (``contentStr``, ``contentBlocks``, ``stopReason``, ``stopSequence``) — NOT
the LLM-API keys (``content`` / ``stop_reason``) that ``Message.model_dump``
emits. Sessions are stored under ``<prefix>session`` using the pydantic
camelCase aliases (``sessionId``, ``userId``, ``deleteTime`` …).

Writes go through :func:`store_base.index_document` (refresh=true, cross-cluster
prefix stripped). Chats/sessions are NOT dual-write audited (Go ``save`` only
indexes the live doc — no history index for the assistant store).

Divergence from Go:

- The Python ``Assistantstore`` port (``src/ports/assistant.py``) takes no
  ``ctx`` argument and performs no ``server.CheckAuthorized`` — authorization
  happens at the FastAPI route/dependency layer — so the Go ``CheckAuthorized``
  calls are dropped. The requestor id (Go ``web.ContextKeyRequestorId``) is
  supplied to the constructor and stamped onto each saved object's ``userId``.
- Consequently the per-session ``filterSharedSessions`` authorization pass
  (which gates owned/shared/other sessions on ``read_authored``/``read_shared``/
  ``read_all``) is dropped — there is no ctx to authorize against. The rest of
  ``GetSessions`` (soft-delete filter, term filters, range, ordering,
  partial-malformed-hit skipping, ``addMetaFromMessages`` update-time
  enrichment) is preserved.

Task 18 implements ``save_chat`` / ``get_chat_history`` / ``create_session`` /
``get_sessions`` (+ ``addMetaFromMessages``) / ``update_session_tags`` /
``delete_session``. Task 19 adds the usage aggregations (``populate_session_usage``
+ ``get_usage``).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from elasticsearch import AsyncElasticsearch

from src.adapters.elasticsearch.client import ElasticClients
from src.adapters.elasticsearch.config import ElasticConfig
from src.adapters.elasticsearch.converter import convert_object_to_document_map
from src.adapters.elasticsearch.escaping import validate_id
from src.adapters.elasticsearch.helpers import disable_cross_cluster_index
from src.adapters.elasticsearch.store_base import index_document
from src.domain.assistant import (
    AssistantSession,
    ContentBlock,
    GetSessionsQuery,
    Message,
    StoredMessage,
    Usage,
)

logger = logging.getLogger(__name__)


def _rfc3339(dt: datetime) -> str:
    """Format like Go ``time.Format(time.RFC3339)`` (offset preserved, no micros)."""
    s = dt.strftime("%Y-%m-%dT%H:%M:%S")
    off = dt.utcoffset()
    if off is None or off.total_seconds() == 0:
        return s + "Z"
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{s}{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def _saveable_message(msg: Message) -> dict[str, Any]:
    """Port of Go ``saveableMessage`` (model/assistant.go:70).

    Always emits ``contentStr`` and ``contentBlocks`` (no omitempty); ``thoughts``
    / ``stopReason`` / ``stopSequence`` / ``usage`` are omitted when empty/None.
    These are the camelCase *storage* keys — not the LLM-API ``content`` /
    ``stop_reason`` keys produced by ``Message.model_dump``.
    """
    out: dict[str, Any] = {
        "id": msg.id,
        "role": msg.role,
        "contentStr": msg.content_str,
        "contentBlocks": [
            cb.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)
            for cb in msg.content_blocks
        ],
    }
    if msg.thoughts:
        out["thoughts"] = msg.thoughts
    if msg.stop_reason is not None:
        out["stopReason"] = msg.stop_reason
    if msg.stop_sequence is not None:
        out["stopSequence"] = msg.stop_sequence
    if msg.usage is not None:
        out["usage"] = msg.usage.model_dump(by_alias=True)
    return out


def _parse_stored_message(chat: dict[str, Any]) -> StoredMessage:
    """Inverse of :func:`_saveable_stored_message` (Go ``StoredMessage.Unmarshal``).

    Reconstructs a ``StoredMessage`` from the camelCase storage shape. The nested
    ``message`` cannot be round-tripped via ``model_validate`` because the
    ``Message`` model's ``content_str`` / ``content_blocks`` carry no storage
    aliases, so the storage keys are read explicitly.
    """
    raw_msg = chat.get("message") or {}
    message = Message(
        id=raw_msg.get("id", ""),
        role=raw_msg.get("role", ""),
        content_str=raw_msg.get("contentStr", ""),
        content_blocks=[
            ContentBlock.model_validate(cb)
            for cb in raw_msg.get("contentBlocks") or []
        ],
        thoughts=raw_msg.get("thoughts", ""),
        stop_reason=raw_msg.get("stopReason"),
        stop_sequence=raw_msg.get("stopSequence"),
        usage=(
            Usage.model_validate(raw_msg["usage"])
            if isinstance(raw_msg.get("usage"), dict)
            else None
        ),
    )
    return StoredMessage(
        sessionId=chat.get("sessionId", ""),
        tags=chat.get("tags") or [],
        model=chat.get("model", ""),
        message=message,
        userId=chat.get("userId", ""),
        createTime=chat.get("createTime"),
        updateTime=chat.get("updateTime"),
    )


def _saveable_stored_message(chat: StoredMessage) -> dict[str, Any]:
    """Port of Go ``StoredMessage.MarshalJSON`` (model/assistant.go:81).

    Flattens the Auditable fields and nests the message under ``message`` with
    the storage (camelCase) keys. ``createTime``/``updateTime`` are RFC3339; nil
    times and empty optional fields are omitted (Go ``omitempty``).
    """
    out: dict[str, Any] = {
        "id": chat.id,
        "userId": chat.user_id,
        "sessionId": chat.session_id,
        "message": _saveable_message(chat.message) if chat.message else {},
    }
    if chat.create_time is not None:
        out["createTime"] = _rfc3339(chat.create_time)
    if chat.update_time is not None:
        out["updateTime"] = _rfc3339(chat.update_time)
    if chat.tags:
        out["tags"] = chat.tags
    if chat.model:
        out["model"] = chat.model
    return out


class ElasticAssistantstore:
    """Assistantstore port backed by an ``AsyncElasticsearch`` client."""

    def __init__(
        self,
        clients: ElasticClients,
        config: ElasticConfig,
        requestor_id: str = "",
    ) -> None:
        self._clients = clients
        self._config = config
        self._requestor_id = requestor_id

    @property
    def _es(self) -> AsyncElasticsearch:
        return self._clients.read_client

    @property
    def _chat_index(self) -> str:
        return self._config.assistant_chat_index

    @property
    def _session_index(self) -> str:
        return self._config.assistant_session_index

    @property
    def _prefix(self) -> str:
        return self._config.schema_prefix

    # ------------------------------------------------------------------
    # validation (Go validateChat / validateSession)
    # ------------------------------------------------------------------

    def _validate_chat(self, chat: StoredMessage) -> str | None:
        """Port of ``validateChat`` (elasticassistantstore.go:155).

        Validates the session id, drops empty ``text`` content blocks in place,
        and requires exactly one of ``contentBlocks`` / ``contentStr``. A content
        block missing both a type and a tool result is rejected.
        """
        err = validate_id(chat.session_id, "SessionId")
        if err:
            return err
        msg = chat.message
        if msg is None:
            return "message must have exactly one content type: either ContentBlocks or ContentStr"

        content_count = 0
        if msg.content_blocks:
            content_count += 1
            keepers = []
            filtered = False
            for cb in msg.content_blocks:
                if cb.type == "" and cb.tool_result is None:
                    return "every content block must have a type"
                if not (cb.type == "text" and cb.text == ""):
                    keepers.append(cb)
                else:
                    filtered = True
            if filtered:
                msg.content_blocks = keepers
        if msg.content_str != "":
            content_count += 1
        if content_count != 1:
            return (
                "message must have exactly one content type: "
                "either ContentBlocks or ContentStr"
            )
        return None

    def _validate_session(self, session: AssistantSession) -> str | None:
        """Port of ``validateSession`` (elasticassistantstore.go:195)."""
        err = validate_id(session.session_id, "SessionId")
        if err:
            return err
        if session.title == "":
            return "Title is too short"
        return None

    # ------------------------------------------------------------------
    # save (Go save/indexDoc) — live write only, no audit
    # ------------------------------------------------------------------

    def _prepare_for_save(self, obj: Any, body: dict[str, Any]) -> dict[str, Any]:
        """Port of ``prepareForSave`` (elasticassistantstore.go:129).

        Stamps the requestor id onto the stored body, strips the (server-owned)
        ``id`` and ``updateTime`` so they are not persisted in the source.
        """
        body["userId"] = self._requestor_id
        body["id"] = ""
        body.pop("updateTime", None)
        return body

    async def _save(self, body: dict[str, Any], index: str, kind: str) -> str:
        """Port of ``save`` (elasticassistantstore.go:51).

        Wraps the body under ``<prefix><kind>`` with ``@timestamp`` and a
        ``<prefix>kind`` tag, then indexes it (refresh=true). Returns the new id.
        """
        document = convert_object_to_document_map(kind, body, self._prefix)
        document[self._prefix + "kind"] = kind
        result = await index_document(self._es, index, document, "")
        return result.document_id

    # ------------------------------------------------------------------
    # public Assistantstore API
    # ------------------------------------------------------------------

    async def save_chat(self, message: StoredMessage) -> None:
        """Port of ``SaveChat`` (elasticassistantstore.go:208)."""
        err = self._validate_chat(message)
        if err:
            raise RuntimeError(err)
        message.create_time = datetime.now()
        message.user_id = self._requestor_id
        body = self._prepare_for_save(message, _saveable_stored_message(message))
        await self._save(body, self._chat_index, "chat")

    async def create_session(self, session: AssistantSession) -> None:
        """Port of ``CreateSession`` (elasticassistantstore.go:973)."""
        err = self._validate_session(session)
        if err:
            raise RuntimeError(err)
        session.create_time = datetime.now()
        session.user_id = self._requestor_id
        body = self._prepare_for_save(
            session, session.model_dump(by_alias=True, exclude_none=True),
        )
        await self._save(body, self._session_index, "session")

    async def get_chat_history(self, session_id: str) -> list[StoredMessage]:
        """Port of ``GetChatHistory`` (elasticassistantstore.go:226).

        Confirms the session exists (including soft-deleted sessions), then loads
        all chat docs for the session ordered by ``@timestamp`` ascending. Raises
        ``"Object not found"`` when no such session exists.
        """
        existing = await self.get_sessions(
            GetSessionsQuery(session_id=session_id, include_deleted=True),
        )
        if not existing:
            raise RuntimeError("Object not found")

        prefix = self._prefix
        chat_query: dict[str, Any] = {"bool": {"must": [
            {"term": {prefix + "chat.sessionId": session_id}},
            {"term": {prefix + "kind": "chat"}},
        ]}}
        resp = await self._es.search(
            index=self._chat_index,
            query=chat_query,
            sort=[{"@timestamp": {"order": "asc"}}],
            size=10000,
        )
        messages: list[StoredMessage] = []
        for hit in dict(resp).get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            chat = source.get(prefix + "chat")
            if not isinstance(chat, dict):
                continue
            stored = _parse_stored_message(chat)
            stored.id = hit.get("_id", "")
            messages.append(stored)
        return messages

    async def get_sessions(
        self, query: GetSessionsQuery,
    ) -> list[AssistantSession]:
        """Port of ``GetSessions`` (elasticassistantstore.go:375).

        Builds the term/range/soft-delete query, parses session hits (skipping
        malformed ones), then always enriches update times via
        ``addMetaFromMessages`` (Go calls it unconditionally). Per-session usage
        enrichment (``with_usage``) is deferred to Task 19.
        """
        prefix = self._prefix
        must: list[dict[str, Any]] = [{"term": {prefix + "kind": "session"}}]
        if query.user_id:
            must.append({"term": {prefix + "session.userId": query.user_id}})
        if query.session_id:
            must.append({"term": {prefix + "session.sessionId": query.session_id}})

        bool_query: dict[str, Any] = {"must": must}
        if not query.include_deleted:
            bool_query["must_not"] = [
                {"exists": {"field": prefix + "session.deleteTime"}},
            ]
        if query.start is not None and query.end is not None:
            must.append({"range": {"@timestamp": {
                "gte": _rfc3339(query.start),
                "lte": _rfc3339(query.end),
            }}})

        resp = await self._es.search(
            index=self._session_index,
            query={"bool": bool_query},
            sort=[{"@timestamp": {"order": "asc"}}],
            size=10000,
        )
        sessions: list[AssistantSession] = []
        for hit in dict(resp).get("hits", {}).get("hits", []):
            source = hit.get("_source", {})
            sess = source.get(prefix + "session")
            if not isinstance(sess, dict):
                continue
            session = AssistantSession.model_validate(sess)
            session.id = hit.get("_id", "")
            sessions.append(session)

        await self._add_meta_from_messages(sessions)
        return sessions

    async def _add_meta_from_messages(
        self, sessions: list[AssistantSession],
    ) -> None:
        """Port of ``addMetaFromMessages`` (elasticassistantstore.go:845).

        Issues one size-0 ``max(createTime)`` aggregation per session via msearch
        and sets each session's ``update_time`` from ``value_as_string``. Empty
        session lists short-circuit; a per-response ``error`` is skipped.

        The msearch targets the full cross-cluster ``_chat_index`` (Go
        ``elasticassistantstore.go:906`` uses ``store.chatIndex`` un-stripped) so
        ``update_time`` enrichment covers chats on remote clusters too. As with
        every read path in this adapter (``get_chat_history`` /
        ``get_sessions`` / ``eventstore.search``), the cross-cluster prefix is
        NOT stripped — only writes/``update_by_query`` strip it via
        ``disable_cross_cluster_index``.
        """
        if not sessions:
            return

        prefix = self._prefix
        searches: list[dict[str, Any]] = []
        for session in sessions:
            searches.append({})  # header line (default index)
            searches.append({
                "query": {"bool": {"must": [
                    {"term": {prefix + "chat.sessionId": session.session_id}},
                    {"term": {prefix + "kind": "chat"}},
                ]}},
                "aggs": {"update_time": {"max": {
                    "field": prefix + "chat.createTime",
                    "format": "strict_date_optional_time",
                }}},
                "size": 0,
            })

        resp = await self._es.msearch(index=self._chat_index, searches=searches)
        responses = dict(resp).get("responses", [])
        for i, sub in enumerate(responses):
            if i >= len(sessions):
                break
            if not isinstance(sub, dict) or "error" in sub:
                continue
            aggs = sub.get("aggregations", {})
            agg = aggs.get("update_time", {})
            value = agg.get("value_as_string")
            if isinstance(value, str):
                sessions[i].update_time = datetime.fromisoformat(
                    value.replace("Z", "+00:00"),
                )

    async def update_session_tags(
        self, session_id: str, tags: list[str],
    ) -> None:
        """Port of ``UpdateSessionTags`` (elasticassistantstore.go:991).

        Owner-scoped (sessionId + requestor userId) ``update_by_query`` with a
        painless script replacing ``<prefix>session.tags`` from a param.
        """
        prefix = self._prefix
        body: dict[str, Any] = {
            "query": {"bool": {"must": [
                {"term": {prefix + "session.sessionId": session_id}},
                {"term": {prefix + "session.userId": self._requestor_id}},
            ]}},
            "script": {
                "source": (
                    "ctx._source." + prefix + "session.tags = params.tags;"
                ),
                "lang": "painless",
                "params": {"tags": tags},
            },
        }
        await self._es.update_by_query(
            index=disable_cross_cluster_index(self._session_index),
            query=body["query"],
            script=body["script"],
            refresh=True,
            wait_for_completion=True,
        )

    async def delete_session(self, session_id: str) -> None:
        """Port of ``DeleteSession`` (elasticassistantstore.go:1061).

        Soft delete: owner-scoped ``update_by_query`` with a painless script
        stamping ``<prefix>session.deleteTime`` to now (RFC3339).
        """
        prefix = self._prefix
        now_str = _rfc3339(datetime.now())
        body: dict[str, Any] = {
            "query": {"bool": {"must": [
                {"term": {prefix + "session.sessionId": session_id}},
                {"term": {prefix + "session.userId": self._requestor_id}},
            ]}},
            "script": {
                "source": (
                    "ctx._source." + prefix
                    + "session.deleteTime = params.deleteTime;"
                ),
                "lang": "painless",
                "params": {"deleteTime": now_str},
            },
        }
        await self._es.update_by_query(
            index=disable_cross_cluster_index(self._session_index),
            query=body["query"],
            script=body["script"],
            refresh=True,
            wait_for_completion=True,
        )
