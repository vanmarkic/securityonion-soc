"""Event domain models — ported from Go model/event.go."""

from __future__ import annotations

from datetime import UTC, datetime

from src.domain.query import Query


def _parse_datetime(s: str, fmt: str, tz_name: str) -> tuple[datetime | None, str | None]:
    """Parse a datetime string using the given format, in the given timezone."""
    import zoneinfo

    try:
        _loc = zoneinfo.ZoneInfo(tz_name)
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        _loc = zoneinfo.ZoneInfo("UTC")

    try:
        # Python's %z handles timezone offsets in the string itself
        dt = datetime.strptime(s.strip(), fmt)
        return dt, None
    except ValueError as e:
        return None, str(e)


def _parse_date_range(
    date_range: str, fmt: str, tz_name: str,
) -> tuple[datetime | None, datetime | None, str | None]:
    """Parse a date range string separated by ' - '."""
    parts = date_range.split(" - ", 1)
    if len(parts) != 2:
        now = datetime.now(UTC)
        from datetime import timedelta
        begin = now - timedelta(hours=24)
        return begin, now, None

    start, err = _parse_datetime(parts[0], fmt, tz_name)
    if err is not None:
        return None, None, err

    end, err = _parse_datetime(parts[1], fmt, tz_name)
    if err is not None:
        return None, None, err

    return start, end, None


# ---------------------------------------------------------------------------
# EventResults base
# ---------------------------------------------------------------------------

class EventResults:
    def __init__(self) -> None:
        self.create_time: datetime = datetime.now(UTC)
        self.complete_time: datetime = datetime.min.replace(tzinfo=UTC)
        self.elapsed_ms: int = 0
        self.errors: list[str] = []

    def complete(self) -> None:
        self.complete_time = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Search criteria & results
# ---------------------------------------------------------------------------

class SortCriteria:
    def __init__(self, field: str = "", order: str = "") -> None:
        self.field = field
        self.order = order


class EventSearchCriteria:
    def __init__(self) -> None:
        self.raw_query: str = ""
        self.date_range: str = ""
        self.metric_limit: int = 10
        self.event_limit: int = 25
        self.begin_time: datetime | None = None
        self.end_time: datetime | None = None
        self.create_time: datetime = datetime.now(UTC)
        self.parsed_query: Query = Query()
        self.sort_fields: list[SortCriteria] = []
        self.search_after: list[object] = []

    def populate(
        self, query: str, date_range: str, date_range_format: str,
        timezone_name: str, metric_limit: str, event_limit: str,
    ) -> str | None:
        self.raw_query = query.strip()

        begin, end, err = _parse_date_range(date_range, date_range_format, timezone_name)
        if err is not None:
            return err
        self.begin_time = begin
        self.end_time = end

        try:
            self.metric_limit = int(metric_limit)
        except ValueError as e:
            return str(e)

        try:
            self.event_limit = int(event_limit)
        except ValueError as e:
            return str(e)

        parse_err = self.parsed_query.parse(query)
        if parse_err is not None:
            return parse_err

        return None


class EventSearchResults(EventResults):
    def __init__(self) -> None:
        super().__init__()
        self.criteria: EventSearchCriteria | None = None
        self.total_events: int = 0
        self.events: list[EventRecord] = []
        self.metrics: dict[str, list[EventMetric]] = {}


class EventMetric:
    def __init__(self) -> None:
        self.keys: list[object] = []
        self.value: float = 0.0
        self.ratio: float = 0.0
        self.percentage: float = 0.0


class EventRecord:
    def __init__(self) -> None:
        self.source: str = ""
        self.time: datetime | None = None
        self.timestamp: str = ""
        self.id: str = ""
        self.type: str = ""
        self.score: float = 0.0
        self.payload: dict[str, object] = {}
        self.sort: list[object] = []


# ---------------------------------------------------------------------------
# Update criteria & results
# ---------------------------------------------------------------------------

class EventUpdateCriteria(EventSearchCriteria):
    def __init__(self) -> None:
        super().__init__()
        self.update_scripts: list[str] = []
        self.params: dict[str, object] = {}
        self.asynchronous: bool = False

    def add_update_script(self, script: str) -> None:
        self.update_scripts.append(script)


class EventUpdateResults(EventResults):
    def __init__(self) -> None:
        super().__init__()
        self.criteria: EventUpdateCriteria | None = None
        self.updated_count: int = 0
        self.unchanged_count: int = 0

    def add_event_update_results(self, new_results: EventUpdateResults) -> None:
        self.updated_count += new_results.updated_count
        self.unchanged_count += new_results.unchanged_count
        self.elapsed_ms += new_results.elapsed_ms


# ---------------------------------------------------------------------------
# MSearch results
# ---------------------------------------------------------------------------

class EventMSearchResults:
    def __init__(self) -> None:
        self.elapsed_ms: int = 0
        self.responses: list[EventSearchResults] = []


# ---------------------------------------------------------------------------
# Ack criteria
# ---------------------------------------------------------------------------

class EventAckCriteria:
    def __init__(self) -> None:
        self.search_filter: str = ""
        self.event_filter: dict[str, object] = {}
        self.date_range: str = ""
        self.date_range_format: str = ""
        self.timezone: str = ""
        self.escalate: bool = False
        self.acknowledge: bool = False


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def new_event_search_criteria() -> EventSearchCriteria:
    return EventSearchCriteria()


def new_event_update_criteria() -> EventUpdateCriteria:
    return EventUpdateCriteria()


def new_event_search_results() -> EventSearchResults:
    return EventSearchResults()


def new_event_update_results() -> EventUpdateResults:
    return EventUpdateResults()


def new_event_ack_criteria() -> EventAckCriteria:
    return EventAckCriteria()
