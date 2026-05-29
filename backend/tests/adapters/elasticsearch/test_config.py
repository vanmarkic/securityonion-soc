from src.adapters.elasticsearch.config import ElasticConfig


def test_defaults_match_go_module():
    c = ElasticConfig()
    assert c.host_url == "elasticsearch"
    assert c.remote_host_urls == []
    assert c.verify_cert is True
    assert c.username == ""
    assert c.password == ""
    assert c.time_shift_ms == 120000
    assert c.default_duration_ms == 1800000
    assert c.es_search_offset_ms == 1800000
    assert c.timeout_ms == 300000
    assert c.cache_ms == 86400000
    assert c.index == "*:so-*"
    assert c.async_threshold == 10
    assert c.intervals == 25
    assert c.max_log_length == 1024
    assert c.cases_enabled is True
    assert c.detections_enabled is True
    assert c.assistant_enabled is True
    assert c.max_scroll_size == 10000
    # sub-store indices
    assert c.case_index == "*:so-case"
    assert c.audit_index == "*:so-casehistory"
    assert c.max_case_associations == 1000
    assert c.schema_prefix == "so_"
    assert c.detection_index == "*:so-detection"
    assert c.detection_audit_index == "*:so-detectionhistory"
    assert c.assistant_chat_index == "*:so-assistant-chat"
    assert c.assistant_session_index == "*:so-assistant-session"


def test_timeout_zero_coerced_to_default():
    c = ElasticConfig(timeout_ms=0)
    assert c.timeout_ms == 300000
