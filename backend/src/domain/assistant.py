"""Assistant domain models — ported from Go model/assistant.go and model/tool.go."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


MESSAGE_TAG_CONTEXT_COMPRESSION = "context_compression"


class ToolResultContent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    json_data: Any | None = Field(default=None, alias="json")
    text: str = ""


class ToolResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    tool_use_id: str = Field(default="", alias="toolUseId")
    content: list[ToolResultContent] = Field(default_factory=list)
    status: str = ""
    is_error: bool = Field(default=False, alias="isError")


class ContentBlock(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: str = ""
    id: str = ""
    name: str = ""
    input: Any | None = None
    json_data: Any | None = Field(default=None, alias="json")
    content: Any | None = None
    text: str = ""
    tool_result: ToolResult | None = Field(default=None, alias="toolResult")
    thought_signature: str | None = Field(default=None, alias="thought_signature")


class Usage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input_tokens: int = Field(default=0, alias="input_tokens")
    output_tokens: int = Field(default=0, alias="output_tokens")
    credits: int = 0


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    role: str = ""
    content_str: str = ""
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    thoughts: str = ""
    stop_reason: str | None = Field(default=None, alias="stop_reason")
    stop_sequence: str | None = Field(default=None, alias="stop_sequence")
    usage: Usage | None = None

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Custom serialization matching Go's MarshalJSON.

        If content_str is set, serialize content as a plain string.
        Otherwise, serialize content_blocks as the content array.
        """
        kwargs.setdefault("by_alias", True)
        kwargs.setdefault("exclude_none", True)
        data: dict[str, Any] = {}
        if self.id:
            data["id"] = self.id
        data["role"] = self.role

        if self.content_str:
            data["content"] = self.content_str
        elif self.content_blocks:
            data["content"] = [cb.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True) for cb in self.content_blocks]

        if self.thoughts:
            data["thoughts"] = self.thoughts
        if self.stop_reason is not None:
            data["stop_reason"] = self.stop_reason
        if self.stop_sequence is not None:
            data["stop_sequence"] = self.stop_sequence
        if self.usage is not None:
            data["usage"] = self.usage.model_dump(by_alias=True)

        return data

    def prepare_for_storage(
        self, session_id: str, tags: list[str] | None, model: str,
    ) -> StoredMessage:
        return StoredMessage(
            session_id=session_id,
            message=self,
            tags=tags or [],
            model=model,
        )


class Auditable(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    create_time: datetime | None = Field(default=None, alias="createTime")
    update_time: datetime | None = Field(default=None, alias="updateTime")
    user_id: str = Field(default="", alias="userId")
    kind: str = ""
    operation: str = ""


class StoredMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(default="", alias="sessionId")
    tags: list[str] = Field(default_factory=list)
    model: str = ""
    message: Message | None = None
    # Auditable fields
    id: str = ""
    create_time: datetime | None = Field(default=None, alias="createTime")
    update_time: datetime | None = Field(default=None, alias="updateTime")
    user_id: str = Field(default="", alias="userId")


class IncomingMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    msg: str = ""
    session_id: str = Field(default="", alias="sessionId")
    model: str = ""
    tags: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    messages: list[Message] = Field(default_factory=list)
    max_tokens: int = Field(default=0, alias="max_tokens")
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 40
    stop_sequences: list[str] = Field(default_factory=list, alias="stop_sequences")
    system: str = ""
    stream: bool = False
    tool_config: Any | None = Field(default=None, alias="toolConfig")
    user_id: str = Field(default="", alias="user_uuid")
    system_append: str = Field(default="", alias="system_append")
    model_name: str = Field(default="", alias="model")


class ModelUsageStats(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model_input_tokens: int = Field(default=0, alias="modelInputTokens")
    model_output_tokens: int = Field(default=0, alias="modelOutputTokens")
    model_credits: int = Field(default=0, alias="modelCredits")
    model_messages: int = Field(default=0, alias="modelMessages")


class SessionUsage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    total_input_tokens: int = Field(default=0, alias="totalInputTokens")
    total_output_tokens: int = Field(default=0, alias="totalOutputTokens")
    total_credits: int = Field(default=0, alias="totalCredits")
    total_messages: int = Field(default=0, alias="totalMessages")
    model_usage: dict[str, ModelUsageStats] | None = Field(default=None, alias="modelUsage")


class AssistantSession(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Auditable
    id: str = ""
    create_time: datetime | None = Field(default=None, alias="createTime")
    update_time: datetime | None = Field(default=None, alias="updateTime")
    user_id: str = Field(default="", alias="userId")

    title: str = ""
    session_id: str = Field(default="", alias="sessionId")
    delete_time: datetime | None = Field(default=None, alias="deleteTime")
    type: str = ""
    entity_id: str = Field(default="", alias="entityId")
    tags: list[str] = Field(default_factory=list)
    usage: SessionUsage | None = None


class AssistantSessionDetails(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session: AssistantSession | None = None
    history: list[StoredMessage] | None = None


class UserUsage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(default="", alias="userId")
    total_input_tokens: int = Field(default=0, alias="totalInputTokens")
    total_output_tokens: int = Field(default=0, alias="totalOutputTokens")
    total_credits: int = Field(default=0, alias="totalCredits")
    total_sessions: int = Field(default=0, alias="totalSessions")
    total_messages: int = Field(default=0, alias="totalMessages")
    model_usage: dict[str, ModelUsageStats] | None = Field(default=None, alias="modelUsage")


class UpdateSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action: str = ""
    tag: str = ""


class ToolRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(default="", alias="sessionId")
    tool_use_id: str = Field(default="", alias="toolUseId")
    params: Any | None = None
    model: str = ""
    aux_data: Any | None = Field(default=None, alias="auxData")


class ToolResponse(BaseModel):
    tool_name: str = ""
    parameters: Any | None = None
    result: Any | None = None
    time_to_execute: float = 0.0
    on_behalf_of_user: str = ""


class BalanceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key_id: str = Field(default="", alias="api_key_prefix")
    company_id: str = Field(default="", alias="company_id")
    status: str = ""
    balance: int = Field(default=0, alias="credit_balance")
    health_status: str = Field(default="", alias="health_status")


class HealthResponse(BaseModel):
    status: str = ""


class GetSessionsQuery(BaseModel):
    """Query parameters for GetSessions, replacing Go's functional options."""

    user_id: str = ""
    session_id: str = ""
    include_deleted: bool = False
    with_usage: bool = False
    start: datetime | None = None
    end: datetime | None = None
