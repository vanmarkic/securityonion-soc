"""Tests for ClientParameters domain models — ported from Go model/clientparameters_test.go."""

import json

from src.domain.clientparameters import (
    DEFAULT_CHART_LABEL_FIELD_SEPARATOR,
    DEFAULT_CHART_LABEL_MAX_LENGTH,
    DEFAULT_CHART_LABEL_OTHER_LIMIT,
    DEFAULT_EVENT_FETCH_LIMIT,
    DEFAULT_GROUP_FETCH_LIMIT,
    DEFAULT_RELATIVE_TIME_UNIT,
    DEFAULT_RELATIVE_TIME_VALUE,
    DEFAULT_SAFE_STRING_MAX_LENGTH,
    CaseParameters,
    ClientParameters,
    DetectionsParameters,
    HuntingAction,
    HuntingParameters,
    ModelParameters,
)


def _verify_initial_hunting_params(params: HuntingParameters):
    """Helper matching verifyInitialHuntingParams in Go."""
    assert params.group_fetch_limit == DEFAULT_GROUP_FETCH_LIMIT
    assert params.event_fetch_limit == DEFAULT_EVENT_FETCH_LIMIT
    assert params.relative_time_value == DEFAULT_RELATIVE_TIME_VALUE
    assert params.relative_time_unit == DEFAULT_RELATIVE_TIME_UNIT
    assert params.safe_string_max_length == DEFAULT_SAFE_STRING_MAX_LENGTH
    assert params.chart_label_max_length == DEFAULT_CHART_LABEL_MAX_LENGTH
    assert params.chart_label_other_limit == DEFAULT_CHART_LABEL_OTHER_LIMIT
    assert params.chart_label_field_separator == DEFAULT_CHART_LABEL_FIELD_SEPARATOR
    assert params.most_recently_used_limit == 0
    assert params.escalate_related_events_enabled is False
    assert params.escalate_enabled is False
    assert params.aggregation_actions_enabled is False


class TestVerifyClientParameters:
    """Ported from TestVerifyClientParameters."""

    def test_default_verify(self):
        params = ClientParameters()
        err = params.verify()
        assert err is None
        assert params.web_socket_timeout_ms == 0
        assert params.tip_timeout_ms == 0
        assert params.api_timeout_ms == 0
        assert params.cache_expiration_ms == 0
        assert params.cases_enabled is False
        assert params.detections_enabled is False
        _verify_initial_hunting_params(params.hunting_params)
        _verify_initial_hunting_params(params.alerting_params)
        _verify_initial_hunting_params(params.cases_params)
        _verify_initial_hunting_params(params.dashboards_params)


class TestVerifyHuntingParams:
    """Ported from TestVerifyHuntingParams."""

    def test_default_verify(self):
        params = HuntingParameters()
        err = params.verify()
        assert err is None
        _verify_initial_hunting_params(params)


class TestCombineDeprecatedLink:
    """Ported from TestCombineEmptyDeprecatedLinkIntoEmptyLinks,
    TestCombineDeprecatedLinkIntoEmptyLinks,
    TestCombineDeprecatedLinkIntoNonEmptyLinks."""

    def test_empty_deprecated_link_into_empty_links(self):
        action = HuntingAction()
        params = HuntingParameters(actions=[action])
        params.combine_deprecated_link_into_links()
        assert len(action.links) == 0

    def test_deprecated_link_into_empty_links(self):
        action = HuntingAction()
        params = HuntingParameters(actions=[action])
        params.combine_deprecated_link_into_links()
        assert len(action.links) == 0

        action.link = "test"
        params.combine_deprecated_link_into_links()
        assert len(action.links) == 1
        assert action.link == ""

    def test_deprecated_link_into_non_empty_links(self):
        action = HuntingAction()
        params = HuntingParameters(actions=[action])
        params.combine_deprecated_link_into_links()

        action.link = "test"
        action.links.append("new-item")
        params.combine_deprecated_link_into_links()
        assert len(action.links) == 2
        assert action.link == ""


class TestVerifyCaseParams:
    """Ported from TestVerifyCaseParams."""

    def test_negative_mru_limit_clamped_to_zero(self):
        params = CaseParameters(most_recently_used_limit=-1)
        err = params.verify()
        assert err is None
        assert params.most_recently_used_limit == 0


class TestVerifyDetectionsParams:
    """Ported from TestVerifyDetectionsParams."""

    def test_default_verify(self):
        params = DetectionsParameters()
        err = params.verify()
        assert err is None
        _verify_initial_hunting_params(params)


class TestModelParametersUnmarshalJSON:
    """Ported from TestModelParameters_UnmarshalJSON."""

    def test_normal_integers(self):
        data = {
            "id": "abc",
            "displayName": "Normal",
            "contextLimitSmall": 512,
            "contextLimitLarge": 2048,
            "charsPerTokenEstimate": 3.6,
            "lowBalanceColorAlert": 7,
        }
        m = ModelParameters.from_json(data)
        assert m.id == "abc"
        assert m.display_name == "Normal"
        assert m.context_limit_small == 512
        assert m.context_limit_large == 2048
        assert m.chars_per_token_estimate == 3.6
        assert m.low_balance_color_alert == 7

    def test_scientific_notation_as_strings(self):
        data = {
            "id": "sci",
            "displayName": "Sci Notation",
            "contextLimitSmall": "1e3",
            "contextLimitLarge": "2e6",
            "lowBalanceColorAlert": "3e4",
        }
        m = ModelParameters.from_json(data)
        assert m.id == "sci"
        assert m.display_name == "Sci Notation"
        assert m.context_limit_small == 1000
        assert m.context_limit_large == 2000000
        assert m.low_balance_color_alert == 30000

    def test_string_integers(self):
        data = {
            "id": "str",
            "displayName": "String Ints",
            "contextLimitSmall": "1234",
            "contextLimitLarge": "5678",
            "lowBalanceColorAlert": "9",
        }
        m = ModelParameters.from_json(data)
        assert m.id == "str"
        assert m.display_name == "String Ints"
        assert m.context_limit_small == 1234
        assert m.context_limit_large == 5678
        assert m.low_balance_color_alert == 9

    def test_mixed_numeric_and_string(self):
        data = {
            "id": "mix",
            "displayName": "Mixed",
            "contextLimitSmall": 8000,
            "contextLimitLarge": "9e3",
            "lowBalanceColorAlert": "4",
        }
        m = ModelParameters.from_json(data)
        assert m.id == "mix"
        assert m.display_name == "Mixed"
        assert m.context_limit_small == 8000
        assert m.context_limit_large == 9000
        assert m.low_balance_color_alert == 4

    def test_invalid_numeric_string(self):
        data = {
            "id": "bad",
            "displayName": "Invalid",
            "contextLimitSmall": "notanumber",
            "contextLimitLarge": "1e2",
        }
        try:
            ModelParameters.from_json(data)
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_missing_context_fields_default_to_zero(self):
        data = {
            "id": "missing",
            "displayName": "Missing Fields",
        }
        m = ModelParameters.from_json(data)
        assert m.id == "missing"
        assert m.display_name == "Missing Fields"
        assert m.context_limit_small == 0
        assert m.context_limit_large == 0
        assert m.chars_per_token_estimate == 0.0
        assert m.low_balance_color_alert == 0

    def test_weird_types_error(self):
        data = {
            "id": "weird",
            "displayName": "Weird Types",
            "contextLimitSmall": False,
            "contextLimitLarge": True,
        }
        try:
            ModelParameters.from_json(data)
            assert False, "Expected ValueError"
        except ValueError:
            pass

    def test_missing_low_balance_defaults_to_zero(self):
        data = {
            "id": "abc",
            "displayName": "Normal",
            "contextLimitSmall": 512,
            "contextLimitLarge": 2048,
        }
        m = ModelParameters.from_json(data)
        assert m.id == "abc"
        assert m.display_name == "Normal"
        assert m.context_limit_small == 512
        assert m.context_limit_large == 2048
        assert m.low_balance_color_alert == 0
