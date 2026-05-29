"""Query DSL parser — ported from Go model/query.go.

Provides a state-machine parser for the Security Onion query language
supporting search, groupby, sortby, and table segments separated by pipes.
"""

from __future__ import annotations

FILTER_INCLUDE = "INCLUDE"
FILTER_EXCLUDE = "EXCLUDE"
FILTER_EXACT = "EXACT"
FILTER_DRILLDOWN = "DRILLDOWN"

SEGMENT_KIND_SEARCH = "search"
SEGMENT_KIND_GROUP_BY = "groupby"
SEGMENT_KIND_SORT_BY = "sortby"
SEGMENT_KIND_TABLE = "table"


def is_scalar(value: object) -> bool:
    """Return True for numeric and boolean values (matching Go's IsScalar)."""
    return isinstance(value, (bool, int, float)) and not (isinstance(value, bool) and False)


def _sanitize(field: str) -> str:
    return field.strip(" \n\t")


# ---------------------------------------------------------------------------
# QueryTerm
# ---------------------------------------------------------------------------

class QueryTerm:
    def __init__(self, raw: str, *, quoted: bool = False, quote: str = "", grouped: bool = False) -> None:
        self.raw = _sanitize(raw)
        self.quoted = quoted
        self.quote = quote
        self.grouped = grouped

    def __str__(self) -> str:
        parts: list[str] = []
        if self.grouped:
            parts.append("(")
        if self.quoted:
            parts.append(self.quote)
        parts.append(self.raw)
        if self.quoted:
            parts.append(self.quote)
        if self.grouped:
            parts.append(")")
        return "".join(parts)


def _new_query_term(raw: str) -> tuple[QueryTerm | None, str | None]:
    field = _sanitize(raw)
    if len(field) == 0:
        return None, "ERROR_QUERY_INVALID__TERM_MISSING"
    return QueryTerm(field), None


# ---------------------------------------------------------------------------
# Segment base + concrete types
# ---------------------------------------------------------------------------

class BaseSegment:
    _kind: str = ""

    def __init__(self, terms: list[QueryTerm] | None = None) -> None:
        self._terms: list[QueryTerm] = terms if terms is not None else []

    @property
    def terms(self) -> list[QueryTerm]:
        return self._terms

    def kind(self) -> str:
        return self._kind

    def terms_as_string(self) -> str:
        return " ".join(str(t) for t in self._terms)

    def clear(self) -> None:
        self._terms = []

    def remove_terms_with(self, raw: str) -> int:
        removed = 0
        found = True
        while found:
            found = False
            for idx, term in enumerate(self._terms):
                if raw in term.raw:
                    self._terms = self._terms[:idx] + self._terms[idx + 1:]
                    found = True
                    removed += 1
                    break
        return removed

    def raw_fields(self) -> list[str]:
        return [t.raw for t in self._terms]

    def fields(self) -> list[str]:
        return [str(t) for t in self._terms]

    def add_field(self, field: str) -> str | None:
        for term in self._terms:
            if term.raw == field:
                return None  # already included
        term, err = _new_query_term(field)
        if err is not None:
            return err
        term.quoted = True
        term.quote = '"'
        self._terms.append(term)
        return None


class SearchSegment(BaseSegment):
    _kind = SEGMENT_KIND_SEARCH

    @classmethod
    def empty(cls) -> SearchSegment:
        return cls([])

    def __str__(self) -> str:
        return self.terms_as_string()

    @staticmethod
    def _escape(value: str) -> str:
        value = value.replace("\\", "\\\\")
        value = value.replace('"', '\\"')
        return value

    def add_filter(self, field: str, value: str, scalar: bool, inclusive: bool, condense: bool) -> str | None:
        if len(field) > 4 and field[:4] == "soc_":
            field = field[3:]

        if value == "__missing__":
            value = field
            field = "_exists_"
            inclusive = not inclusive

        if condense:
            condensed, _ = _new_query_term(str(self))
            condensed.grouped = True
            self.clear()
            self._terms.append(condensed)

        if len(self._terms) > 0:
            and_term, _ = _new_query_term("AND")
            self._terms.append(and_term)
        if not inclusive:
            not_term, _ = _new_query_term("NOT")
            self._terms.append(not_term)

        builder: list[str] = []
        if len(field) > 0:
            builder.append(field)
            builder.append(":")
        if not scalar:
            builder.append('"')
            builder.append(self._escape(value))
            builder.append('"')
        else:
            builder.append(value)

        term, err = _new_query_term("".join(builder))
        if err is not None:
            return err
        self._terms.append(term)
        return None


def _new_search_segment(terms: list[QueryTerm]) -> tuple[SearchSegment | None, str | None]:
    if len(terms) == 0:
        return None, "ERROR_QUERY_INVALID__SEARCH_TERMS_MISSING"
    return SearchSegment(terms), None


class GroupBySegment(BaseSegment):
    _kind = SEGMENT_KIND_GROUP_BY

    def __init__(self, terms: list[QueryTerm] | None = None) -> None:
        if terms is not None and len(terms) == 0:
            raise ValueError("ERROR_QUERY_INVALID__GROUPBY_TERMS_MISSING")
        super().__init__(terms)

    @classmethod
    def empty(cls) -> GroupBySegment:
        seg = object.__new__(cls)
        BaseSegment.__init__(seg, [])
        return seg

    def __str__(self) -> str:
        return self.kind() + " " + self.terms_as_string()


def _new_group_by_segment(terms: list[QueryTerm]) -> tuple[GroupBySegment | None, str | None]:
    if len(terms) == 0:
        return None, "ERROR_QUERY_INVALID__GROUPBY_TERMS_MISSING"
    return GroupBySegment(terms), None


class SortBySegment(BaseSegment):
    _kind = SEGMENT_KIND_SORT_BY

    def __init__(self, terms: list[QueryTerm] | None = None) -> None:
        if terms is not None and len(terms) == 0:
            raise ValueError("ERROR_QUERY_INVALID__SORTBY_TERMS_MISSING")
        super().__init__(terms)

    @classmethod
    def empty(cls) -> SortBySegment:
        seg = object.__new__(cls)
        BaseSegment.__init__(seg, [])
        return seg

    def __str__(self) -> str:
        return self.kind() + " " + self.terms_as_string()


def _new_sort_by_segment(terms: list[QueryTerm]) -> tuple[SortBySegment | None, str | None]:
    if len(terms) == 0:
        return None, "ERROR_QUERY_INVALID__SORTBY_TERMS_MISSING"
    return SortBySegment(terms), None


class TableSegment(BaseSegment):
    _kind = SEGMENT_KIND_TABLE

    def __init__(self, terms: list[QueryTerm] | None = None) -> None:
        if terms is not None and len(terms) == 0:
            raise ValueError("ERROR_QUERY_INVALID__TABLE_TERMS_MISSING")
        super().__init__(terms)

    @classmethod
    def empty(cls) -> TableSegment:
        seg = object.__new__(cls)
        BaseSegment.__init__(seg, [])
        return seg

    def __str__(self) -> str:
        return self.kind() + " " + self.terms_as_string()


def _new_table_segment(terms: list[QueryTerm]) -> tuple[TableSegment | None, str | None]:
    if len(terms) == 0:
        return None, "ERROR_QUERY_INVALID__TABLE_TERMS_MISSING"
    return TableSegment(terms), None


def _new_segment(kind: str, terms: list[QueryTerm]) -> tuple[BaseSegment | None, str | None]:
    if kind == SEGMENT_KIND_SEARCH:
        return _new_search_segment(terms)
    if kind == SEGMENT_KIND_GROUP_BY:
        return _new_group_by_segment(terms)
    if kind == SEGMENT_KIND_SORT_BY:
        return _new_sort_by_segment(terms)
    if kind == SEGMENT_KIND_TABLE:
        return _new_table_segment(terms)
    return None, "ERROR_QUERY_INVALID__SEGMENT_UNSUPPORTED"


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

class Query:
    def __init__(self) -> None:
        self.segments: list[BaseSegment] = []

    def named_segment(self, name: str) -> BaseSegment | None:
        for seg in self.segments:
            if seg.kind() == name:
                return seg
        return None

    def named_segments(self, name: str) -> list[BaseSegment]:
        return [s for s in self.segments if s.kind() == name]

    def add_segment(self, segment: BaseSegment) -> None:
        self.segments.append(segment)

    def remove_segment(self, name: str) -> BaseSegment | None:
        for idx, seg in enumerate(self.segments):
            if seg.kind() == name:
                self.segments = self.segments[:idx] + self.segments[idx + 1:]
                return seg
        return None

    # ----- Parser (state machine) -----

    def parse(self, raw: str) -> str | None:  # noqa: C901 — direct port of Go
        current_terms: list[QueryTerm] = []
        current_kind = SEGMENT_KIND_SEARCH
        builder: list[str] = []
        escaping = False
        quoting = False
        grouping = 0
        quoting_char = " "

        for ch in raw:
            if not quoting:
                if grouping == 0:
                    if not escaping and ch in ('"', "'"):
                        if len(builder) > 0:
                            term, err = _new_query_term("".join(builder))
                            if err:
                                return err
                            current_terms.append(term)
                            builder.clear()
                        quoting = True
                        quoting_char = ch
                    elif not escaping and ch == "|":
                        if len(builder) > 0:
                            term, err = _new_query_term("".join(builder))
                            if err:
                                return err
                            current_terms.append(term)
                            builder.clear()
                        if len(current_terms) == 0:
                            return "ERROR_QUERY_INVALID__SEGMENT_EMPTY"
                        if current_kind == "":
                            current_kind = str(current_terms[0])
                            current_terms = current_terms[1:]
                        seg, err = _new_segment(current_kind, current_terms)
                        if err:
                            return err
                        self.add_segment(seg)
                        current_kind = ""
                        current_terms = []
                    elif not escaping and ch in (" ", ",", "\n", "\t"):
                        if len(builder) > 0:
                            term, err = _new_query_term("".join(builder))
                            if err:
                                return err
                            current_terms.append(term)
                            builder.clear()
                    elif not escaping and ch == "(":
                        grouping += 1
                    elif not escaping and ch == ")":
                        return "ERROR_QUERY_INVALID__GROUP_NOT_STARTED"
                    else:
                        builder.append(ch)
                elif not escaping and ch == ")" and grouping == 1:
                    if len(builder) == 0:
                        return "ERROR_QUERY_INVALID__GROUP_EMPTY"
                    term, err = _new_query_term("".join(builder))
                    if err:
                        return err
                    term.grouped = True
                    current_terms.append(term)
                    builder.clear()
                    grouping = 0
                else:
                    if ch == "(":
                        grouping += 1
                    elif ch == ")":
                        grouping -= 1
                    builder.append(ch)
            elif not escaping and ch == quoting_char:
                term, err = _new_query_term("".join(builder))
                if err:
                    return err
                term.quoted = quoting
                term.quote = quoting_char
                current_terms.append(term)
                builder.clear()
                quoting = False
            else:
                builder.append(ch)

            if not escaping and ch == "\\":
                escaping = True
            else:
                escaping = False

        if quoting:
            return "ERROR_QUERY_INVALID__QUOTE_INCOMPLETE"
        if grouping > 0:
            return "ERROR_QUERY_INVALID__GROUP_INCOMPLETE"

        if len(builder) > 0:
            term, err = _new_query_term("".join(builder))
            if err:
                return err
            term.quoted = quoting
            term.grouped = grouping > 0
            term.quote = quoting_char
            current_terms.append(term)

        if len(current_terms) > 0:
            if current_kind == "":
                current_kind = str(current_terms[0])
                current_terms = current_terms[1:]
            seg, err = _new_segment(current_kind, current_terms)
            if err:
                return err
            self.add_segment(seg)

        if len(self.segments) == 0:
            return "ERROR_QUERY_INVALID__SEARCH_MISSING"

        return None

    def __str__(self) -> str:
        return " | ".join(str(s) for s in self.segments)

    # ----- High-level operations -----

    def filter(
        self, field: str, value: str, scalar: bool, mode: str, condense: bool,
    ) -> tuple[str, str | None]:
        seg = self.named_segment(SEGMENT_KIND_SEARCH)
        if seg is None:
            seg = SearchSegment.empty()
            self.add_segment(seg)
        search_seg: SearchSegment = seg  # type: ignore[assignment]

        if mode == FILTER_EXACT:
            search_seg.clear()

        inclusive = mode != FILTER_EXCLUDE
        err = search_seg.add_filter(field, value, scalar, inclusive, condense)

        if mode == FILTER_DRILLDOWN:
            removed = self.remove_segment(SEGMENT_KIND_GROUP_BY)
            while removed is not None:
                removed = self.remove_segment(SEGMENT_KIND_GROUP_BY)

        return str(self), err

    def group(self, segment_idx: int, field: str) -> tuple[str, str | None]:
        segments = self.named_segments(SEGMENT_KIND_GROUP_BY)
        if segment_idx < 0 or len(segments) <= segment_idx:
            gb = GroupBySegment.empty()
            self.add_segment(gb)
        else:
            gb = segments[segment_idx]  # type: ignore[assignment]
        err = gb.add_field(field)
        return str(self), err

    def sort(self, field: str) -> tuple[str, str | None]:
        seg = self.named_segment(SEGMENT_KIND_SORT_BY)
        if seg is None:
            seg = SortBySegment.empty()
            self.add_segment(seg)
        err = seg.add_field(field)
        return str(self), err

    def table(self, field: str) -> tuple[str, str | None]:
        seg = self.named_segment(SEGMENT_KIND_TABLE)
        if seg is None:
            seg = TableSegment.empty()
            self.add_segment(seg)
        err = seg.add_field(field)
        return str(self), err
