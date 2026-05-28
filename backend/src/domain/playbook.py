"""Playbook domain models — ported from Go model/playbook.go."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventRecord(BaseModel):
    """Represents a single event record returned from a query."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class Question(BaseModel):
    """A playbook question that guides investigation."""

    model_config = ConfigDict(populate_by_name=True)

    question: str = ""
    context: str = ""
    range: str | None = None
    answer_sources: list[str] | None = Field(default=None, alias="answer_sources")
    query: str = ""
    filled_query: str = Field(default="", alias="filledQuery")
    query_results: list[EventRecord] | None = Field(default=None, alias="queryResults")
    query_fields: list[str] | None = Field(default=None, alias="fields")
    oql_query: str = Field(default="", alias="oqlQuery")


class Playbook(BaseModel):
    """Represents a Security Onion playbook."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    id: str = ""
    description: str = ""
    source_created: datetime | None = Field(default=None, alias="created")
    source_updated: datetime | None = Field(default=None, alias="modified")
    detection_id: str = Field(default="", alias="detection_id")
    detection_category: str = Field(default="", alias="detection_category")
    detection_type: str = Field(default="", alias="detection_type")
    contributors: list[str] | None = None
    questions: list[Question] | None = None


class ConvertedQuery(BaseModel):
    """The OQL result of a converted Sigma query."""

    model_config = ConfigDict(populate_by_name=True)

    query: str = ""
    fields: list[str] | None = None
