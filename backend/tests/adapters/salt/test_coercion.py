"""Tests for src.adapters.salt.coercion — scalar align_best_guess / align_type.

Anchors to the scalar parsing behaviour exercised by saltstore_test.go's
TestUpdateSetting_Align* / FailToAlign* cases and to Go's strconv semantics.
List branches are deferred to the next unit (B2).
"""

import pytest

from src.adapters.salt.coercion import (
    align_best_guess,
    align_type,
    parse_bool,
    parse_float,
    parse_int,
)


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

    def test_list_branch_deferred_to_b2(self):
        with pytest.raises(NotImplementedError, match="B2"):
            align_best_guess("a\nb")

    def test_json_branch_deferred_to_b2(self):
        with pytest.raises(NotImplementedError, match="B2"):
            align_best_guess('{"a":1}')


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

    def test_str_old_keeps_string(self):
        # AlignNonStringType: old="my_str", new="123" stays the string "123".
        result = align_type("my_str", "123")
        assert result == "123"
        assert isinstance(result, str)

    def test_none_old_uses_best_guess(self):
        # nil old value -> alignBestGuess.
        assert align_type(None, "44") == 44
        assert align_type(None, "hello") == "hello"

    def test_list_old_deferred_to_b2(self):
        with pytest.raises(NotImplementedError, match="B2"):
            align_type([1, 2], "3\n4")
