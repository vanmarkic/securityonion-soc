"""Tests for CustomRuleset domain model — ported from Go model/custom_ruleset_test.go."""

from src.domain.custom_ruleset import CustomRuleset, get_custom_rulesets_default


class TestGetCustomRulesetsDefault:
    """Ported from TestGetCustomRulesetsDefault in custom_ruleset_test.go."""

    def _default_rulesets(self):
        return [
            CustomRuleset(ruleset="default", license="DRL", file="default.rules"),
        ]

    def test_missing_returns_defaults(self):
        dflt = self._default_rulesets()
        out, err = get_custom_rulesets_default({}, "customRulesets", dflt)
        assert err is None
        assert out == dflt

    def test_empty_list(self):
        dflt = self._default_rulesets()
        out, err = get_custom_rulesets_default(
            {"customRulesets": []}, "customRulesets", dflt
        )
        assert err is None
        assert out == []

    def test_nil_value_returns_defaults(self):
        dflt = self._default_rulesets()
        out, err = get_custom_rulesets_default(
            {"customRulesets": None}, "customRulesets", dflt
        )
        assert err is None
        assert out == dflt

    def test_valid(self):
        cfg = {
            "customRulesets": [
                {
                    "community": True,
                    "url": "https://example.com",
                    "target-file": "example.rules",
                    "ruleset": "example",
                    "license": "MIT",
                },
                {
                    "community": 1,
                    "file": "example2.rules",
                    "ruleset": "example2",
                    "license": "MIT",
                },
                {
                    "community": "T",
                    "url": "https://example3.com",
                    "target-file": "example3.rules",
                    "ruleset": "example3",
                    "license": "MIT",
                },
                {
                    "community": "definitely",
                    "url": "https://example4.com",
                    "target-file": "example4.rules",
                    "ruleset": "example4",
                    "license": "DRL",
                },
            ],
        }
        out, err = get_custom_rulesets_default(cfg, "customRulesets", [])
        assert err is None
        assert len(out) == 4

        assert out[0].community is True
        assert out[0].url == "https://example.com"
        assert out[0].target_file == "example.rules"
        assert out[0].ruleset == "example"
        assert out[0].license == "MIT"

        assert out[1].community is True
        assert out[1].file == "example2.rules"
        assert out[1].ruleset == "example2"
        assert out[1].license == "MIT"

        assert out[2].community is True
        assert out[2].url == "https://example3.com"
        assert out[2].target_file == "example3.rules"
        assert out[2].ruleset == "example3"
        assert out[2].license == "MIT"

        assert out[3].community is False
        assert out[3].url == "https://example4.com"
        assert out[3].target_file == "example4.rules"
        assert out[3].ruleset == "example4"
        assert out[3].license == "DRL"

    def test_invalid_type(self):
        out, err = get_custom_rulesets_default(
            {"customRulesets": "invalid"}, "customRulesets", []
        )
        assert err is not None
        assert 'top level config value "customRulesets" is not an array of objects' in err

    def test_invalid_entry(self):
        out, err = get_custom_rulesets_default(
            {"customRulesets": ["invalid"]}, "customRulesets", []
        )
        assert err is not None
        assert '"customRulesets" entry is not an object' in err

    def test_invalid_key_value_pairs(self):
        cfg = {
            "customRulesets": [
                {"wrong": "key/value"},
            ],
        }
        out, err = get_custom_rulesets_default(cfg, "customRulesets", [])
        assert err is not None
        assert 'missing "file" or "url"+"target-file" from "customRulesets" entry' in err

    def test_missing_url(self):
        cfg = {
            "customRulesets": [
                {
                    "target-file": "example.rules",
                    "ruleset": "example",
                    "license": "MIT",
                },
            ],
        }
        out, err = get_custom_rulesets_default(cfg, "customRulesets", [])
        assert err is not None
        assert 'missing "url" from "customRulesets" entry' in err

    def test_missing_target(self):
        cfg = {
            "customRulesets": [
                {
                    "url": "https://example.com",
                    "ruleset": "example",
                    "license": "MIT",
                },
            ],
        }
        out, err = get_custom_rulesets_default(cfg, "customRulesets", [])
        assert err is not None
        assert 'missing "target-file" from "customRulesets" entry' in err

    def test_missing_ruleset(self):
        cfg = {
            "customRulesets": [
                {
                    "url": "https://example.com",
                    "target-file": "example.rules",
                    "license": "MIT",
                },
            ],
        }
        out, err = get_custom_rulesets_default(cfg, "customRulesets", [])
        assert err is not None
        assert 'missing "ruleset" from "customRulesets" entry' in err

    def test_missing_license(self):
        cfg = {
            "customRulesets": [
                {
                    "url": "https://example.com",
                    "target-file": "example.rules",
                    "ruleset": "example",
                },
            ],
        }
        out, err = get_custom_rulesets_default(cfg, "customRulesets", [])
        assert err is not None
        assert 'missing "license" from "customRulesets" entry' in err
