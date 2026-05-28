"""Tests for Query DSL parser — ported from Go model/query_test.go."""

import pytest

from src.domain.query import (
    FILTER_DRILLDOWN,
    FILTER_EXACT,
    FILTER_EXCLUDE,
    FILTER_INCLUDE,
    SEGMENT_KIND_GROUP_BY,
    GroupBySegment,
    Query,
    QueryTerm,
    SearchSegment,
    is_scalar,
)


# ---------------------------------------------------------------------------
# Helper: validate_query
# ---------------------------------------------------------------------------

def _validate_query(raw: str, expected: str | None = None) -> None:
    """Parse raw, compare str(query) to expected (defaults to raw)."""
    if expected is None:
        expected = raw
    query = Query()
    err = query.parse(raw)
    if err is not None:
        actual = str(err)
    else:
        actual = str(query)
    assert actual == expected


# ---------------------------------------------------------------------------
# TestQueries — comprehensive parse/round-trip tests
# ---------------------------------------------------------------------------

class TestQueries:
    def test_simple_word(self):
        _validate_query("abc")

    def test_two_words(self):
        _validate_query("abc def")

    def test_colon_with_single_quotes(self):
        _validate_query("abc:'def'", "abc: 'def'")

    def test_leading_trailing_spaces(self):
        _validate_query("   abc0   def  ", "abc0 def")

    def test_single_quoted_first_term(self):
        _validate_query("'abc1' def")

    def test_single_quoted_phrase(self):
        _validate_query("'abc2 def'")

    def test_double_quoted_with_single_inside(self):
        _validate_query('"abc3\' def"')

    def test_comma_separator(self):
        _validate_query("abc5,def", "abc5 def")

    def test_groupby_pipe(self):
        _validate_query("abc def | groupby jkl")

    def test_groupby_quoted_field(self):
        _validate_query("abc def | groupby 'jkl'")

    def test_quoted_pipe_inside(self):
        _validate_query("'abc8 | groupby'")

    def test_trailing_pipe_stripped(self):
        _validate_query("abcA|", "abcA")

    def test_parentheses_and(self):
        _validate_query("(abc AND def)")

    def test_nested_parens(self):
        _validate_query("((abc AND def))")

    def test_complex_grouped(self):
        _validate_query('((abc AND def:"ghi") AND (xyz="123"))')

    def test_pipe_groupby_newline(self):
        _validate_query("abcA|groupby\njjj", "abcA | groupby jjj")

    def test_pipe_groupby_tab(self):
        _validate_query("abcA|\ngroupby\tjjj", "abcA | groupby jjj")

    # --- Error cases ---

    def test_incomplete_single_quote(self):
        _validate_query("'abc4 def", "ERROR_QUERY_INVALID__QUOTE_INCOMPLETE")

    def test_incomplete_quote_with_pipe(self):
        _validate_query("'abc9|", "ERROR_QUERY_INVALID__QUOTE_INCOMPLETE")

    def test_pipe_only(self):
        _validate_query("|", "ERROR_QUERY_INVALID__SEGMENT_EMPTY")

    def test_space_pipe(self):
        _validate_query(" |", "ERROR_QUERY_INVALID__SEGMENT_EMPTY")

    def test_space_pipe_word(self):
        _validate_query(" | abc", "ERROR_QUERY_INVALID__SEGMENT_EMPTY")

    def test_double_pipe(self):
        _validate_query("abc6 def | |", "ERROR_QUERY_INVALID__SEGMENT_EMPTY")

    def test_double_pipe_no_space(self):
        _validate_query("abc7 def || ", "ERROR_QUERY_INVALID__SEGMENT_EMPTY")

    def test_group_not_started(self):
        _validate_query("abc7 def ) ", "ERROR_QUERY_INVALID__GROUP_NOT_STARTED")

    def test_group_empty(self):
        _validate_query("abc7 def () ", "ERROR_QUERY_INVALID__GROUP_EMPTY")

    def test_group_incomplete(self):
        _validate_query("abc (d e f", "ERROR_QUERY_INVALID__GROUP_INCOMPLETE")

    def test_group_incomplete_with_pipes(self):
        _validate_query("abc (d e f | ghi 'jkl' | mno", "ERROR_QUERY_INVALID__GROUP_INCOMPLETE")

    def test_unsupported_segment(self):
        _validate_query("abc (d e f) | groupby 'jkl' | mno", "ERROR_QUERY_INVALID__SEGMENT_UNSUPPORTED")

    def test_empty_string(self):
        _validate_query("", "ERROR_QUERY_INVALID__SEARCH_MISSING")

    def test_only_spaces(self):
        _validate_query(" ", "ERROR_QUERY_INVALID__SEARCH_MISSING")

    def test_groupby_missing_terms(self):
        _validate_query("abcA|groupby", "ERROR_QUERY_INVALID__GROUPBY_TERMS_MISSING")

    def test_groupby_missing_terms_space(self):
        _validate_query("abcA|groupby ", "ERROR_QUERY_INVALID__GROUPBY_TERMS_MISSING")

    # --- sortby ---

    def test_sortby_newline(self):
        _validate_query("abcA|sortby\njjj, lll", "abcA | sortby jjj lll")

    def test_sortby_tab(self):
        _validate_query("abcA|\nsortby\tjjj", "abcA | sortby jjj")

    def test_sortby_missing_terms(self):
        _validate_query("abcA|sortby", "ERROR_QUERY_INVALID__SORTBY_TERMS_MISSING")

    def test_sortby_missing_terms_space(self):
        _validate_query("abcA|sortby ", "ERROR_QUERY_INVALID__SORTBY_TERMS_MISSING")

    # --- table ---

    def test_table_newline(self):
        _validate_query("abcA|table\njjj, lll", "abcA | table jjj lll")

    def test_table_tab(self):
        _validate_query("abcA|\ntable\tjjj", "abcA | table jjj")

    def test_table_missing_terms(self):
        _validate_query("abcA|table", "ERROR_QUERY_INVALID__TABLE_TERMS_MISSING")

    def test_table_missing_terms_space(self):
        _validate_query("abcA|table ", "ERROR_QUERY_INVALID__TABLE_TERMS_MISSING")


# ---------------------------------------------------------------------------
# TestGroupWithQuotes / TestRawFields
# ---------------------------------------------------------------------------

class TestGroupBySegmentFields:
    def test_fields_with_quotes(self):
        query = Query()
        err = query.parse('foo:"bar" | groupby "complex field" "another complex field"')
        assert err is None
        seg = query.named_segment(SEGMENT_KIND_GROUP_BY)
        assert isinstance(seg, GroupBySegment)
        fields = seg.fields()
        assert len(fields) == 2
        assert fields[0] == '"complex field"'
        assert fields[1] == '"another complex field"'

    def test_raw_fields(self):
        query = Query()
        err = query.parse('foo:"bar" | groupby "complex field" "another complex field"')
        assert err is None
        seg = query.named_segment(SEGMENT_KIND_GROUP_BY)
        assert isinstance(seg, GroupBySegment)
        raw = seg.raw_fields()
        assert len(raw) == 2
        assert raw[0] == "complex field"
        assert raw[1] == "another complex field"


# ---------------------------------------------------------------------------
# TestGroup
# ---------------------------------------------------------------------------

def _validate_group(orig: str, group_idx: int, group: str, expected: str) -> None:
    query = Query()
    query.parse(orig)
    actual, err = query.group(group_idx, group)
    if err is not None:
        actual = str(err)
    assert actual == expected


class TestGroup:
    def test_add_first_groupby(self):
        _validate_group("a", 0, "b", 'a | groupby "b"')

    def test_add_field_to_existing(self):
        _validate_group("a|groupby b", 0, "c", 'a | groupby b "c"')

    def test_duplicate_field_no_change(self):
        _validate_group("a|groupby b", 0, "b", "a | groupby b")

    def test_index_past_existing_adds_new(self):
        _validate_group("a|groupby b", 1, "c", 'a | groupby b | groupby "c"')

    def test_index_way_past_adds_new(self):
        _validate_group("a|groupby b", 2, "c", 'a | groupby b | groupby "c"')

    def test_negative_index_adds_new(self):
        _validate_group("a|groupby b", -2, "c", 'a | groupby b | groupby "c"')


# ---------------------------------------------------------------------------
# TestSort
# ---------------------------------------------------------------------------

def _validate_sort(orig: str, sort_field: str, expected: str) -> None:
    query = Query()
    query.parse(orig)
    actual, err = query.sort(sort_field)
    if err is not None:
        actual = str(err)
    assert actual == expected


class TestSort:
    def test_add_sortby(self):
        _validate_sort("a", "b", 'a | sortby "b"')

    def test_add_to_existing_sortby(self):
        _validate_sort("a|sortby b", "c", 'a | sortby b "c"')

    def test_duplicate_sort_no_change(self):
        _validate_sort("a|sortby b", "b", "a | sortby b")


# ---------------------------------------------------------------------------
# TestTable
# ---------------------------------------------------------------------------

def _validate_table(orig: str, table_field: str, expected: str) -> None:
    query = Query()
    query.parse(orig)
    actual, err = query.table(table_field)
    if err is not None:
        actual = str(err)
    assert actual == expected


class TestTable:
    def test_add_table(self):
        _validate_table("a", "b", 'a | table "b"')

    def test_add_to_existing_table(self):
        _validate_table("a|table b", "c", 'a | table b "c"')

    def test_duplicate_table_no_change(self):
        _validate_table("a|table b", "b", "a | table b")


# ---------------------------------------------------------------------------
# TestFilter
# ---------------------------------------------------------------------------

def _validate_filter(
    orig: str, key: str, value: str, scalar: bool,
    mode: str, condense: bool, expected: str,
) -> None:
    query = Query()
    query.parse(orig)
    actual, err = query.filter(key, value, scalar, mode, condense)
    if err is not None:
        actual = str(err)
    assert actual == expected


class TestFilter:
    def test_include(self):
        _validate_filter("a", "b", "c", False, FILTER_INCLUDE, False, 'a AND b:"c"')

    def test_exclude(self):
        _validate_filter("a", "b", "c", False, FILTER_EXCLUDE, False, 'a AND NOT b:"c"')

    def test_include_empty_search(self):
        _validate_filter("", "b", "c", False, FILTER_INCLUDE, False, 'b:"c"')

    def test_include_scalar(self):
        _validate_filter("", "b", "1", True, FILTER_INCLUDE, False, "b:1")

    def test_exact_replaces_search(self):
        _validate_filter(
            "(a:1 OR c:2) | groupby z", "b", "1", True,
            FILTER_EXACT, False, "b:1 | groupby z",
        )

    def test_drilldown_removes_groupby(self):
        _validate_filter(
            "(a:1 OR c:2) | groupby z", "b", "1", True,
            FILTER_DRILLDOWN, False, "(a:1 OR c:2) AND b:1",
        )

    def test_soc_prefix_stripped(self):
        _validate_filter("a", "soc_b", "1", True, FILTER_INCLUDE, False, "a AND _b:1")

    def test_same_field_new_value(self):
        _validate_filter("a:1", "a", "2", True, FILTER_INCLUDE, False, "a:1 AND a:2")

    def test_colon_space(self):
        _validate_filter("a: 1", "a", "2", True, FILTER_INCLUDE, False, "a: 1 AND a:2")

    def test_exclude_with_not(self):
        _validate_filter("NOT a:1", "a", "2", True, FILTER_EXCLUDE, False, "NOT a:1 AND NOT a:2")

    def test_condense(self):
        _validate_filter(
            "a:1 OR b:1", "c", "3", True,
            FILTER_INCLUDE, True, "(a:1 OR b:1) AND c:3",
        )

    def test_drilldown_multiple_groupby(self):
        _validate_filter(
            "* | groupby a | groupby b | groupby c", "b", "d", True,
            FILTER_DRILLDOWN, False, "* AND b:d",
        )


# ---------------------------------------------------------------------------
# TestIsScalar
# ---------------------------------------------------------------------------

class TestIsScalar:
    def test_int_is_scalar(self):
        assert is_scalar(1) is True

    def test_false_is_scalar(self):
        assert is_scalar(False) is True

    def test_true_is_scalar(self):
        assert is_scalar(True) is True

    def test_float_is_scalar(self):
        assert is_scalar(22.1) is True

    def test_string_is_not_scalar(self):
        assert is_scalar("str") is False


# ---------------------------------------------------------------------------
# TestRemoveTermsWith
# ---------------------------------------------------------------------------

class TestRemoveTermsWith:
    def test_empty_segment(self):
        seg = SearchSegment.empty()
        assert seg.remove_terms_with("hello") == 0

    def test_remove_single_match(self):
        seg = SearchSegment.empty()
        seg.add_filter("hello", "a", False, False, False)
        assert seg.remove_terms_with("hello") == 1

    def test_already_removed(self):
        seg = SearchSegment.empty()
        seg.add_filter("hello", "a", False, False, False)
        seg.remove_terms_with("hello")
        assert seg.remove_terms_with("hello") == 0

    def test_unmatched_term(self):
        seg = SearchSegment.empty()
        seg.add_filter("hello", "a", False, False, False)
        seg.remove_terms_with("hello")
        seg.add_filter("there", "b", False, False, False)
        assert seg.remove_terms_with("hello") == 0

    def test_partial_match_removes_multiple(self):
        seg = SearchSegment.empty()
        seg.add_filter("hello", "a", False, False, False)
        seg.remove_terms_with("hello")
        seg.add_filter("there", "b", False, False, False)
        seg.add_filter("and", "c", False, False, False)
        seg.add_filter("goodbye", "d", False, False, False)
        assert seg.remove_terms_with("e") == 2


# ---------------------------------------------------------------------------
# TestNamedSegments
# ---------------------------------------------------------------------------

class TestNamedSegments:
    def test_multiple_groupby_segments(self):
        query = Query()
        t1 = QueryTerm("t1")
        t2 = QueryTerm("t2")
        t3 = QueryTerm("t3")
        segment1 = GroupBySegment([t1, t2])
        query.add_segment(segment1)
        segment2 = GroupBySegment([t3])
        query.add_segment(segment2)
        segments = query.named_segments(SEGMENT_KIND_GROUP_BY)
        assert len(segments) == 2
        assert segments[0] is segment1
        assert segments[1] is segment2
