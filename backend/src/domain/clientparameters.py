"""ClientParameters domain models — ported from Go model/clientparameters.go."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_GROUP_FETCH_LIMIT = 10
DEFAULT_EVENT_FETCH_LIMIT = 100
DEFAULT_RELATIVE_TIME_VALUE = 24
DEFAULT_RELATIVE_TIME_UNIT = 30
DEFAULT_SAFE_STRING_MAX_LENGTH = 100
DEFAULT_CHART_LABEL_MAX_LENGTH = 35
DEFAULT_CHART_LABEL_OTHER_LIMIT = 10
DEFAULT_CHART_LABEL_FIELD_SEPARATOR = ", "


class HuntingAction(BaseModel):
    """Represents an action that can be taken on a hunting result."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    description: str = ""
    icon: str = ""
    link: str = ""
    links: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    target: str = ""
    background: bool = False
    background_success_link: str = Field(default="", alias="backgroundSuccessLink")
    background_failure_link: str = Field(default="", alias="backgroundFailureLink")
    method: str = ""
    body: str = ""
    options: dict[str, Any] = Field(default_factory=dict)
    categories: list[str] = Field(default_factory=list)
    js_call: str = Field(default="", alias="jsCall")


class ToggleFilter(BaseModel):
    """Represents a toggle filter for hunting queries."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = ""
    filter: str = ""
    enabled: bool = False
    exclusive: bool = False
    enables_toggles: list[str] = Field(default_factory=list, alias="enablesToggles")
    disables_toggles: list[str] = Field(default_factory=list, alias="disablesToggles")


class HuntingParameters(BaseModel):
    """Parameters controlling the hunting interface behavior."""

    model_config = ConfigDict(populate_by_name=True)

    group_items_per_page: int = Field(default=0, alias="groupItemsPerPage")
    group_fetch_limit: int = Field(default=0, alias="groupFetchLimit")
    event_items_per_page: int = Field(default=0, alias="eventItemsPerPage")
    event_fetch_limit: int = Field(default=0, alias="eventFetchLimit")
    relative_time_value: int = Field(default=0, alias="relativeTimeValue")
    relative_time_unit: int = Field(default=0, alias="relativeTimeUnit")
    most_recently_used_limit: int = Field(default=0, alias="mostRecentlyUsedLimit")
    event_fields: dict[str, list[str]] = Field(default_factory=dict, alias="eventFields")
    safe_string_max_length: int = Field(default=0, alias="safeStringMaxLength")
    query_base_filter: str = Field(default="", alias="queryBaseFilter")
    query_toggle_filters: list[ToggleFilter] = Field(default_factory=list, alias="queryToggleFilters")
    queries: list[Any] = Field(default_factory=list)
    actions: list[HuntingAction] = Field(default_factory=list)
    advanced: bool = False
    ack_enabled: bool = Field(default=False, alias="ackEnabled")
    escalate_enabled: bool = Field(default=False, alias="escalateEnabled")
    escalate_related_events_enabled: bool = Field(default=False, alias="escalateRelatedEventsEnabled")
    view_enabled: bool = Field(default=False, alias="viewEnabled")
    create_link: str = Field(default="", alias="createLink")
    chart_label_max_length: int = Field(default=0, alias="chartLabelMaxLength")
    chart_label_other_limit: int = Field(default=0, alias="chartLabelOtherLimit")
    chart_label_field_separator: str = Field(default="", alias="chartLabelFieldSeparator")
    aggregation_actions_enabled: bool = Field(default=False, alias="aggregationActionsEnabled")
    detection_engine_status_queries: str = Field(default="", alias="detectionEngineStatusQueries")

    def verify(self) -> str | None:
        """Apply defaults for invalid values. Returns error string or None."""
        if self.group_fetch_limit <= 0:
            self.group_fetch_limit = DEFAULT_GROUP_FETCH_LIMIT
        if self.event_fetch_limit <= 0:
            self.event_fetch_limit = DEFAULT_EVENT_FETCH_LIMIT
        if self.relative_time_value <= 0:
            self.relative_time_value = DEFAULT_RELATIVE_TIME_VALUE
        if self.relative_time_unit <= 0:
            self.relative_time_unit = DEFAULT_RELATIVE_TIME_UNIT
        if self.most_recently_used_limit < 0:
            self.most_recently_used_limit = 0
        if self.safe_string_max_length <= 0:
            self.safe_string_max_length = DEFAULT_SAFE_STRING_MAX_LENGTH
        if self.chart_label_max_length <= 0:
            self.chart_label_max_length = DEFAULT_CHART_LABEL_MAX_LENGTH
        if self.chart_label_other_limit <= 0:
            self.chart_label_other_limit = DEFAULT_CHART_LABEL_OTHER_LIMIT
        if not self.chart_label_field_separator:
            self.chart_label_field_separator = DEFAULT_CHART_LABEL_FIELD_SEPARATOR
        self.combine_deprecated_link_into_links()
        return None

    def combine_deprecated_link_into_links(self) -> None:
        """Migrate deprecated 'link' field into 'links' list on actions."""
        for action in self.actions:
            if action.link:
                action.links.append(action.link)
                action.link = ""


class CaseParameters(BaseModel):
    """Parameters for case management."""

    model_config = ConfigDict(populate_by_name=True)

    most_recently_used_limit: int = Field(default=0, alias="mostRecentlyUsedLimit")
    render_abbreviated_count: int = Field(default=0, alias="renderAbbreviatedCount")
    analyzer_node_id: str = Field(default="", alias="analyzerNodeId")
    presets: dict[str, Any] = Field(default_factory=dict)

    def verify(self) -> str | None:
        """Apply defaults. Returns error string or None."""
        if self.most_recently_used_limit < 0:
            self.most_recently_used_limit = 0
        return None


class DetectionsParameters(HuntingParameters):
    """Parameters for detections view, extending HuntingParameters."""

    presets: dict[str, Any] = Field(default_factory=dict)

    def verify(self) -> str | None:
        """Apply defaults via parent verify. Returns error string or None."""
        return super().verify()


class ModelParameters(BaseModel):
    """AI model parameters with custom parsing for numeric/string fields."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default="", alias="id")
    display_name: str = Field(default="", alias="displayName")
    context_limit_small: int = Field(default=0, alias="contextLimitSmall")
    context_limit_large: int = Field(default=0, alias="contextLimitLarge")
    chars_per_token_estimate: float = Field(default=0.0, alias="charsPerTokenEstimate")
    low_balance_color_alert: int = Field(default=0, alias="lowBalanceColorAlert")
    origin: str = ""
    adapter: str = ""
    enabled: bool = False

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ModelParameters:
        """Parse from a JSON-like dict, handling numeric strings and scientific notation.

        Matches Go's custom UnmarshalJSON behavior.
        """

        def parse_to_int(v: Any) -> int:
            if v is None:
                return 0
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return int(v)
            if isinstance(v, str):
                f = float(v)  # raises ValueError for invalid
                return round(f)
            raise ValueError(f"unexpected type {type(v).__name__} for numeric field")

        m = cls()
        m.id = data.get("id", "")
        m.display_name = data.get("displayName", "")
        m.chars_per_token_estimate = float(data.get("charsPerTokenEstimate", 0) or 0)
        m.origin = data.get("origin", "")
        m.adapter = data.get("adapter", "")
        m.enabled = data.get("enabled", False)

        m.context_limit_small = parse_to_int(data.get("contextLimitSmall"))
        m.context_limit_large = parse_to_int(data.get("contextLimitLarge"))
        if "lowBalanceColorAlert" in data and data["lowBalanceColorAlert"] is not None:
            m.low_balance_color_alert = parse_to_int(data["lowBalanceColorAlert"])

        return m


class ClientParameters(BaseModel):
    """Top-level client configuration parameters."""

    model_config = ConfigDict(populate_by_name=True)

    hunting_params: HuntingParameters = Field(default_factory=HuntingParameters, alias="hunt")
    alerting_params: HuntingParameters = Field(default_factory=HuntingParameters, alias="alerts")
    cases_params: HuntingParameters = Field(default_factory=HuntingParameters, alias="cases")
    case_params: CaseParameters = Field(default_factory=CaseParameters, alias="case")
    dashboards_params: HuntingParameters = Field(default_factory=HuntingParameters, alias="dashboards")
    job_params: HuntingParameters = Field(default_factory=HuntingParameters, alias="job")
    detections_params: DetectionsParameters = Field(default_factory=DetectionsParameters, alias="detections")
    docs_url: str = Field(default="", alias="docsUrl")
    cheatsheet_url: str = Field(default="", alias="cheatsheetUrl")
    release_notes_url: str = Field(default="", alias="releaseNotesUrl")
    web_socket_timeout_ms: int = Field(default=0, alias="webSocketTimeoutMs")
    tip_timeout_ms: int = Field(default=0, alias="tipTimeoutMs")
    api_timeout_ms: int = Field(default=0, alias="apiTimeoutMs")
    cache_expiration_ms: int = Field(default=0, alias="cacheExpirationMs")
    inactive_tools: list[str] = Field(default_factory=list, alias="inactiveTools")
    cases_enabled: bool = Field(default=False, alias="casesEnabled")
    detections_enabled: bool = Field(default=False, alias="detectionsEnabled")
    export_node_id: str = Field(default="", alias="exportNodeId")

    def verify(self) -> str | None:
        """Verify all sub-parameters. Returns error string or None."""
        err = self.hunting_params.verify()
        if err:
            return err
        err = self.alerting_params.verify()
        if err:
            return err
        err = self.cases_params.verify()
        if err:
            return err
        err = self.dashboards_params.verify()
        if err:
            return err
        return self.job_params.verify()
