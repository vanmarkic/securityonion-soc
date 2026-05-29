from pydantic import BaseModel, Field, field_validator


class ElasticConfig(BaseModel):
    host_url: str = "elasticsearch"
    remote_host_urls: list[str] = Field(default_factory=list)
    extract_common_observables: list[str] = Field(default_factory=list)
    verify_cert: bool = True
    username: str = ""
    password: str = ""
    time_shift_ms: int = 120000
    default_duration_ms: int = 1800000
    es_search_offset_ms: int = 1800000
    timeout_ms: int = 300000
    cache_ms: int = 86400000
    index: str = "*:so-*"
    async_threshold: int = 10
    intervals: int = 25
    max_log_length: int = 1024
    cases_enabled: bool = True
    lookup_tunnel_parent: bool = True
    detections_enabled: bool = True
    assistant_enabled: bool = True
    max_scroll_size: int = 10000
    # sub-store indices
    case_index: str = "*:so-case"
    audit_index: str = "*:so-casehistory"
    max_case_associations: int = 1000
    # Per-case cap on related events attached in a single bulk escalate, ported
    # from Go's ``ClientParams.AlertingParams.MaxBulkEscalateEvents`` — a config
    # value distinct from ``max_case_associations``. Go's elasticcasestore_test
    # exercises this with 100; this is the production-configured frontend cap,
    # not the 1000-default association limit.
    max_bulk_escalate_events: int = 100
    schema_prefix: str = "so_"
    detection_index: str = "*:so-detection"
    detection_audit_index: str = "*:so-detectionhistory"
    max_detection_associations: int = 1000
    assistant_chat_index: str = "*:so-assistant-chat"
    assistant_session_index: str = "*:so-assistant-session"
    bulk_indexer_worker_count: int = -1

    @field_validator("timeout_ms")
    @classmethod
    def _coerce_timeout(cls, v: int) -> int:
        return 300000 if v == 0 else v
