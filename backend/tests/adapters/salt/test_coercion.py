"""Tests for src.adapters.salt.coercion — align_best_guess / align_type + lists.

Anchors to the scalar AND list parsing behaviour exercised by saltstore_test.go's
TestUpdateSetting_Align* / FailToAlign* / Force* cases and to Go's strconv
semantics.
"""

import pytest

from src.adapters.salt.coercion import (
    align_best_guess,
    align_best_guess_list,
    align_bool_list,
    align_float64_list,
    align_int64_list,
    align_list_list,
    align_map_list,
    align_type,
    coerce_map_list_field_types,
    force_type,
    interface_to_string,
    parse_bool,
    parse_float,
    parse_int,
    zero_for_type,
)
from src.domain.config import UiElement


class TestParseInt:
    @pytest.mark.parametrize("value,expected", [("44", 44), ("-3", -3), ("+7", 7), ("0", 0)])
    def test_valid(self, value: str, expected: int):
        assert parse_int(value) == expected

    @pytest.mark.parametrize("value", ["not an int", "3.5", "", " 5", "0x10", "1_000"])
    def test_invalid_matches_go_error(self, value: str):
        with pytest.raises(ValueError, match=rf'strconv\.ParseInt: parsing "{value}": invalid syntax'):
            parse_int(value)


class TestParseFloat:
    @pytest.mark.parametrize("value,expected", [("44.2", 44.2), ("1.2", 1.2), ("3", 3.0), ("-0.5", -0.5)])
    def test_valid(self, value: str, expected: float):
        assert parse_float(value) == expected

    @pytest.mark.parametrize("value", ["not a float", "", " 1.2"])
    def test_invalid_matches_go_error(self, value: str):
        with pytest.raises(ValueError, match=rf'strconv\.ParseFloat: parsing "{value}": invalid syntax'):
            parse_float(value)


class TestParseBool:
    @pytest.mark.parametrize("value", ["1", "t", "T", "TRUE", "true", "True"])
    def test_truthy(self, value: str):
        assert parse_bool(value) is True

    @pytest.mark.parametrize("value", ["0", "f", "F", "FALSE", "false", "False"])
    def test_falsy(self, value: str):
        assert parse_bool(value) is False

    @pytest.mark.parametrize("value", ["not a bool", "yes", "no", "2", ""])
    def test_invalid_matches_go_error(self, value: str):
        with pytest.raises(ValueError, match=rf'strconv\.ParseBool: parsing "{value}": invalid syntax'):
            parse_bool(value)


class TestAlignBestGuess:
    def test_int_first(self):
        result = align_best_guess("42")
        assert result == 42
        assert isinstance(result, int)

    def test_float_when_not_int(self):
        result = align_best_guess("4.2")
        assert result == 4.2
        assert isinstance(result, float)

    def test_bool_when_not_numeric(self):
        assert align_best_guess("true") is True
        assert align_best_guess("false") is False

    def test_string_fallback(self):
        assert align_best_guess("hello") == "hello"

    def test_newline_list_branch(self):
        # \n in the value -> alignBestGuessList; "a","b" best-guess to strings.
        assert align_best_guess("a\nb") == ["a", "b"]

    def test_newline_int_list_branch(self):
        # First line best-guesses int -> the whole value coerces to an int list.
        assert align_best_guess("1\n2\n3") == [1, 2, 3]

    def test_json_object_branch(self):
        assert align_best_guess('{"a":1}') == {"a": 1}

    def test_json_array_branch(self):
        assert align_best_guess("[1,2,3]") == [1, 2, 3]

    def test_malformed_json_object_stays_string(self):
        # A {...} that fails to JSON-decode falls through and stays a string.
        assert align_best_guess("{not json}") == "{not json}"


class TestAlignIntList:
    def test_parses_each_line(self):
        assert align_int64_list("44\n2\n1") == [44, 2, 1]

    def test_empty_input_yields_empty_list(self):
        assert align_int64_list("") == []

    def test_bad_line_raises(self):
        with pytest.raises(ValueError, match=r'strconv\.ParseInt: parsing "invalid": invalid syntax'):
            align_int64_list("1\n2\ninvalid")


class TestAlignBoolList:
    def test_parses_each_line(self):
        assert align_bool_list("true\nfalse\ntrue") == [True, False, True]

    def test_empty_input_yields_empty_list(self):
        assert align_bool_list("") == []

    def test_bad_line_raises(self):
        with pytest.raises(ValueError, match=r'strconv\.ParseBool: parsing "hi": invalid syntax'):
            align_bool_list("true\nfalse\nhi")


class TestAlignFloatList:
    def test_parses_each_line(self):
        assert align_float64_list("44.3\n2.1\n1.2") == [44.3, 2.1, 1.2]

    def test_empty_input_yields_empty_list(self):
        assert align_float64_list("") == []

    def test_bad_line_raises(self):
        with pytest.raises(ValueError, match=r'strconv\.ParseFloat: parsing "nope": invalid syntax'):
            align_float64_list("1.2\nnope")


class TestAlignListList:
    def test_parses_each_json_array_line(self):
        assert align_list_list('["item1","item2"]\n["item3","item4"]') == [
            ["item1", "item2"],
            ["item3", "item4"],
        ]

    def test_empty_input_yields_empty_list(self):
        assert align_list_list("") == []

    def test_non_array_line_raises(self):
        # A bool line is valid JSON but not a list -> raises.
        with pytest.raises(ValueError):
            align_list_list("true\nfalse")

    def test_malformed_line_raises(self):
        with pytest.raises(ValueError):
            align_list_list("cannot set list of strings\non list of lists")


class TestAlignMapList:
    def test_parses_each_json_object_line(self):
        assert align_map_list('{"k":"v1"}\n{"k":"v2"}') == [{"k": "v1"}, {"k": "v2"}]

    def test_empty_input_yields_empty_list(self):
        assert align_map_list("") == []

    def test_non_object_line_raises(self):
        with pytest.raises(ValueError):
            align_map_list("true\nfalse")

    def test_malformed_line_raises(self):
        with pytest.raises(ValueError):
            align_map_list("cannot set list of strings\non list of maps")


class TestInterfaceToString:
    def test_string_as_is(self):
        assert interface_to_string("hello") == "hello"

    def test_whole_float_renders_as_int(self):
        assert interface_to_string(8080.0) == "8080"

    def test_fractional_float(self):
        assert interface_to_string(4.2) == "4.2"

    def test_bool_lowercase(self):
        assert interface_to_string(True) == "true"
        assert interface_to_string(False) == "false"

    def test_int(self):
        assert interface_to_string(42) == "42"

    def test_list_joins_with_newline(self):
        assert interface_to_string(["a", "b", "c"]) == "a\nb\nc"


class TestAlignBestGuessList:
    def test_empty_input(self):
        assert align_best_guess_list("") == []

    def test_int_first_dispatches_int_list(self):
        assert align_best_guess_list("1\n2\n3") == [1, 2, 3]

    def test_bool_first_dispatches_bool_list(self):
        assert align_best_guess_list("true\nfalse") == [True, False]

    def test_float_first_dispatches_float_list(self):
        assert align_best_guess_list("1.5\n2.5") == [1.5, 2.5]

    def test_list_first_dispatches_list_list(self):
        assert align_best_guess_list('["a"]\n["b"]') == [["a"], ["b"]]

    def test_map_first_dispatches_map_list(self):
        assert align_best_guess_list('{"k":1}\n{"k":2}') == [{"k": 1}, {"k": 2}]

    def test_string_first_returns_raw_split(self):
        assert align_best_guess_list("foo\nbar") == ["foo", "bar"]


class TestZeroForType:
    @pytest.mark.parametrize(
        "typ,expected",
        [
            ("float", 0.0),
            ("int", 0),
            ("bool", False),
            ("string", ""),
            ("[]int", []),
            ("[]bool", []),
            ("[]float", []),
            ("[]string", []),
            ("[][]", []),
            ("[]{}", []),
        ],
    )
    def test_zero(self, typ: str, expected: object):
        assert zero_for_type(typ) == expected

    def test_unknown_type_is_none(self):
        assert zero_for_type("nope") is None


class TestForceType:
    def test_float(self):
        assert force_type("44.2", "float") == 44.2

    def test_int(self):
        assert force_type("44", "int") == 44

    def test_bool(self):
        assert force_type("true", "bool") is True

    def test_string(self):
        assert force_type("anything", "string") == "anything"

    def test_int_list(self):
        assert force_type("1\n2", "[]int") == [1, 2]

    def test_bool_list(self):
        assert force_type("true\nfalse", "[]bool") == [True, False]

    def test_float_list(self):
        assert force_type("1.1\n2.2", "[]float") == [1.1, 2.2]

    def test_string_list(self):
        assert force_type("a\nb", "[]string") == ["a", "b"]

    def test_string_list_empty(self):
        assert force_type("", "[]string") == []

    def test_list_list(self):
        assert force_type('["a"]\n["b"]', "[][]") == [["a"], ["b"]]

    def test_map_list(self):
        assert force_type('{"k":1}', "[]{}") == [{"k": 1}]

    def test_unsupported_raises(self):
        with pytest.raises(ValueError, match="Unsupported forced type: nope"):
            force_type("x", "nope")


class TestCoerceMapListFieldTypes:
    def _ui(self, field: str, forced_type: str, *, required: bool = False) -> UiElement:
        el = UiElement()
        el.field = field
        el.forced_type = forced_type
        el.required = required
        return el

    def test_coerces_string_inputs(self):
        # Strings from the UI get re-typed to their declared forcedType.
        list_ = [{"enabled": "true", "name": "alpha", "port": "8080"}]
        ui = [self._ui("port", "int"), self._ui("enabled", "bool"), self._ui("name", "")]
        result = coerce_map_list_field_types(list_, ui)
        assert result == [{"enabled": True, "name": "alpha", "port": 8080}]

    def test_coerces_numeric_float_to_int(self):
        # A JSON-parsed 8080.0 float must become int 8080 for the int forcedType.
        list_ = [{"port": 8080.0}]
        result = coerce_map_list_field_types(list_, [self._ui("port", "int")])
        assert result == [{"port": 8080}]

    def test_missing_field_skipped(self):
        list_ = [{"name": "alpha"}]
        result = coerce_map_list_field_types(list_, [self._ui("port", "int")])
        assert result == [{"name": "alpha"}]

    def test_blank_forced_type_or_field_skipped(self):
        list_ = [{"x": "5"}]
        result = coerce_map_list_field_types(
            list_, [self._ui("x", ""), self._ui("", "int")]
        )
        assert result == [{"x": "5"}]

    def test_optional_failure_resets_to_zero(self):
        # An optional field that fails to coerce is reset to the type's zero value.
        list_ = [{"port": "not a number"}]
        result = coerce_map_list_field_types(
            list_, [self._ui("port", "int", required=False)]
        )
        assert result == [{"port": 0}]

    def test_required_failure_raises(self):
        list_ = [{"port": "not a number"}]
        with pytest.raises(ValueError, match=r'field "port":'):
            coerce_map_list_field_types(
                list_, [self._ui("port", "int", required=True)]
            )


class TestAlignTypeScalar:
    def test_bool_old(self):
        # AlignBoolType: old=True, new="false" -> False.
        assert align_type(True, "false") is False

    def test_bool_old_fail(self):
        # FailToAlignBoolType.
        with pytest.raises(ValueError, match=r'strconv\.ParseBool: parsing "not a bool": invalid syntax'):
            align_type(True, "not a bool")

    def test_int_old(self):
        # AlignIntType: old=123, new="44" -> 44.
        result = align_type(123, "44")
        assert result == 44
        assert isinstance(result, int)

    def test_int_old_fail(self):
        # FailToAlignIntType.
        with pytest.raises(ValueError, match=r'strconv\.ParseInt: parsing "not an int": invalid syntax'):
            align_type(123, "not an int")

    def test_float_old(self):
        # AlignFloatType: old=3.5, new="44.2" -> 44.2.
        result = align_type(3.5, "44.2")
        assert result == 44.2
        assert isinstance(result, float)

    def test_float_old_fail(self):
        # FailToAlignFloatType.
        with pytest.raises(ValueError, match=r'strconv\.ParseFloat: parsing "not a float": invalid syntax'):
            align_type(3.5, "not a float")

    def test_str_old_routes_to_best_guess(self):
        # Go's alignType has NO `case string`; a str oldValue falls through to the
        # trailing `return alignBestGuess(newValue)`. So a non-numeric string stays
        # a string...
        result = align_type("my_str", "stays string")
        assert result == "stays string"
        assert isinstance(result, str)

    def test_str_old_numeric_input_best_guesses_to_int(self):
        # ...but a numeric-looking new value best-guesses to int (Go int64), since
        # there is no string short-circuit. (Read-back via render_scalar still
        # stringifies to "123", so AlignNonStringType's assertion holds.)
        result = align_type("my_str", "123")
        assert result == 123
        assert isinstance(result, int)

    def test_none_old_uses_best_guess(self):
        # nil old value -> alignBestGuess.
        assert align_type(None, "44") == 44
        assert align_type(None, "hello") == "hello"

    def test_list_old_int_dispatches_int_list(self):
        # old=[3, 24] (first elem int) -> int list coercion.
        assert align_type([3, 24], "44\n2\n1") == [44, 2, 1]

    def test_list_old_bool_dispatches_bool_list(self):
        # bool checked before int (bool subclasses int).
        assert align_type([True, False], "true\nfalse") == [True, False]

    def test_list_old_float_dispatches_float_list(self):
        assert align_type([1.2, 3.4], "5.6\n7.8") == [5.6, 7.8]

    def test_list_old_str_verbatim_split(self):
        # Go's []string case: a raw split, no scalar parsing -> numbers stay strings.
        assert align_type(["foo", "bar"], "123\n456") == ["123", "456"]

    def test_list_old_list_dispatches_list_list(self):
        assert align_type([["a"]], '["x"]\n["y"]') == [["x"], ["y"]]

    def test_list_old_map_dispatches_map_list(self):
        assert align_type([{"k": "v"}], '{"k":"v2"}') == [{"k": "v2"}]

    def test_empty_list_old_best_guesses(self):
        # An empty old list -> alignBestGuessList on the new value.
        assert align_type([], "1\n2") == [1, 2]
        assert align_type([], "foo\nbar") == ["foo", "bar"]
        # A single blank line splits to [""], best-guessing to a string list.
        assert align_type([], "") == []
