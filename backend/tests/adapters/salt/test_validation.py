"""Tests for src.adapters.salt.validation — ported from syntax/validator_test.go.

Anchors to syntax/validator_test.go (TestValidate_Jinja / TestValidate_NoJinja),
yaml_test.go (TestValidate_Yaml), and json_test.go (TestValidate_Json).
"""

import pytest

from src.adapters.salt.validation import validate, validate_json, validate_yaml


class TestValidateJinja:
    @pytest.mark.parametrize(
        "value",
        [
            "Testing Jinja {{ test }}",
            "Alternative {% test %} form",
            "comments {# this is a comment #}",
        ],
    )
    def test_matched_jinja_markers_rejected(self, value: str):
        # Port of TestValidate_Jinja: syntax "na" but matched markers still reject.
        with pytest.raises(ValueError, match="^ERROR_JINJA_NOT_SUPPORTED$"):
            validate(value, "na")

    @pytest.mark.parametrize(
        "value",
        [
            'Testing Jinja {"foo":"bar"}',  # unmatched {{ }} pair
            "Alternative %% foo",
        ],
    )
    def test_unmatched_or_no_jinja_ok(self, value: str):
        # Port of TestValidate_NoJinja: no MATCHED marker pair -> valid.
        validate(value, "na")


class TestValidateYaml:
    @pytest.mark.parametrize("syntax", ["yaml", "yml"])
    def test_good_yaml_ok(self, syntax: str):
        # Port of TestValidate_Yaml good cases.
        validate("valid: yaml", syntax)
        validate("- one\n- two", syntax)
        validate("map_of_list:\n  - one\n  - two", syntax)

    @pytest.mark.parametrize("syntax", ["yaml", "yml"])
    def test_bad_yaml_raises(self, syntax: str):
        with pytest.raises(ValueError, match=r"^ERROR_MALFORMED_YAML -> "):
            validate("[ lksdgf invalid yaml", syntax)

    def test_empty_yaml_is_valid(self):
        validate_yaml("")

    def test_validate_yaml_helper_raises(self):
        with pytest.raises(ValueError, match=r"^ERROR_MALFORMED_YAML -> "):
            validate_yaml("[ lksdgf invalid yaml")


class TestValidateJson:
    @pytest.mark.parametrize("syntax", ["json", "suricata"])
    def test_good_json_ok(self, syntax: str):
        # Port of TestValidate_Json good cases.
        validate('{ "valid": "value" }', syntax)
        validate('[{ "valid": "value" }]', syntax)

    @pytest.mark.parametrize("syntax", ["json", "suricata"])
    def test_bad_json_raises(self, syntax: str):
        with pytest.raises(ValueError, match="^ERROR_MALFORMED_JSON$"):
            validate("invalid vaue", syntax)

    def test_empty_json_is_valid(self):
        validate_json("")

    def test_validate_json_helper_raises(self):
        with pytest.raises(ValueError, match="^ERROR_MALFORMED_JSON$"):
            validate_json("invalid vaue")


class TestValidateNonMatchingSyntax:
    def test_unknown_syntax_accepts_anything(self):
        # Neither yaml nor json -> no validation performed.
        validate("this is not yaml or json: [", "txt")
        validate("", "")
