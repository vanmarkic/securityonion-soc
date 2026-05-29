from datetime import UTC, datetime

from src.adapters.elasticsearch.field_caps import FieldDefinition
from src.adapters.elasticsearch.query_builder import (
    format_search,
    make_query,
    strip_segment_options,
)
from src.domain.query import Query


def test_format_search():
    assert format_search("") == "*"
    assert format_search(" ") == "*"  # strip(' ') only
    assert format_search(r"\foo\bar") == r"\foo\bar"


def test_strip_segment_options():
    assert strip_segment_options(["one", "-flag", "two"]) == ["one", "two"]


def _q(s: str) -> Query:
    q = Query()
    assert q.parse(s) is None
    return q


def test_make_query_no_range_when_end_zero():
    body = make_query({}, _q("*"), None, None)
    assert body == {
        "bool": {
            "filter": [],
            "should": [],
            "must_not": [],
            "must": [
                {
                    "query_string": {
                        "query": "*",
                        "analyze_wildcard": True,
                        "default_field": "*",
                    }
                }
            ],
        }
    }


def test_make_query_with_range_serializes_like_go():
    begin = datetime(2020, 1, 2, 12, 13, 14, tzinfo=UTC)
    end = datetime(2020, 1, 2, 13, 13, 14, tzinfo=UTC)
    body = make_query({}, _q("abc AND def"), begin, end)
    must = body["bool"]["must"]
    assert must[0]["query_string"]["query"] == "abc AND def"
    assert must[1] == {
        "range": {
            "@timestamp": {
                "gte": "2020-01-02T12:13:14Z",
                "lte": "2020-01-02T13:13:14Z",
                "format": "strict_date_optional_time",
            }
        }
    }
    # empty arrays always present
    assert (
        body["bool"]["filter"] == []
        and body["bool"]["should"] == []
        and body["bool"]["must_not"] == []
    )


def test_map_search_remaps_bare_field_colon():
    defs = {
        "foo": FieldDefinition("foo", "text", aggregatable=False, searchable=True),
        "foo.keyword": FieldDefinition(
            "foo.keyword", "keyword", aggregatable=True, searchable=True
        ),
    }
    q = _q('foo: "bar"')
    body = make_query(defs, q, None, None)
    assert body["bool"]["must"][0]["query_string"]["query"] == 'foo.keyword: "bar"'
