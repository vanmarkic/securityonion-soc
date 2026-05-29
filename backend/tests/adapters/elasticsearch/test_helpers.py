from datetime import datetime

from src.adapters.elasticsearch.helpers import (
    AUDIT_DOC_ID,
    LONG_STRING_MAX,
    MAX_ARRAY_ELEMENTS,
    MAX_AUTHOR_LENGTH,
    SHORT_STRING_MAX,
    disable_cross_cluster_index,
    read_error_from_json,
    transform_index,
    truncate,
    validate_string,
    validate_string_array,
    validate_string_required,
)


def test_disable_cross_cluster_index():
    assert disable_cross_cluster_index("*:so-*") == "so-*"
    assert disable_cross_cluster_index("cluster:so-case") == "so-case"
    assert disable_cross_cluster_index("so-case") == "so-case"  # no colon -> unchanged


def test_transform_index_today():
    out = transform_index("logstash-{today}")
    today = datetime.now().strftime("%Y.%m.%d")
    assert out == f"logstash-{today}"


def test_truncate():
    assert truncate("abc", 10) == "abc"
    assert truncate("abcdef", 3) == "abc..."


def test_read_error_from_json_format():
    body = '{"error":{"type":"x_type","reason":"the reason"}}'
    msg = read_error_from_json(body)
    assert msg == 'x_type: the reason -> {"error":{"type":"x_type","reason":"the reason"}}'


def test_read_error_from_json_matches_go_golden():
    # Captured verbatim from Go TestReadErrorFromJson (elasticeventstore_test.go:122).
    body = '{"error":{"type":"some type","reason":"some reason"},"something.else":"yes"}'
    expected = (
        "some type: some reason -> "
        '{"error":{"type":"some type","reason":"some reason"},"something.else":"yes"}'
    )
    assert read_error_from_json(body) == expected


def test_validate_string_lengths():
    assert validate_string("ok", 100, "title") is None
    assert validate_string("x" * 141, 100, "title") == "title is too long (141/100)"
    assert validate_string_required("", 1, 100, "title") == "title is too short (0/1)"


def test_validate_string_array_excess_elements():
    arr = ["a"] * 51
    assert (
        validate_string_array(arr, 100, 50, "tags")
        == "Field 'tags' contains excessive elements (51/50)"
    )
    # Go uses a lowercase literal element label 'tag[idx]' (elasticcasestore.go:107),
    # regardless of the array's own label.
    assert validate_string_array(["x" * 200], 100, 50, "tags") == "tag[0] is too long (200/100)"


def test_module_constants_match_go():
    assert SHORT_STRING_MAX == 100
    assert MAX_AUTHOR_LENGTH == 250
    assert LONG_STRING_MAX == 1000000
    assert MAX_ARRAY_ELEMENTS == 50
    assert AUDIT_DOC_ID == "audit_doc_id"
