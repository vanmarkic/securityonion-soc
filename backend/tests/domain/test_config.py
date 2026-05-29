"""Tests for Setting domain model — ported from Go model/config_test.go."""

from src.domain.config import is_valid_minion_id, is_valid_setting_id, new_setting


class TestNewSetting:
    def test_string_id(self):
        setting = new_setting("MyId")
        assert setting.id == "MyId"
        assert setting.advanced is False


class TestIsValidMinionId:
    def test_alphanumeric(self):
        assert is_valid_minion_id("foo") is True

    def test_with_hyphen(self):
        assert is_valid_minion_id("foo-bar") is True

    def test_mixed_case_hyphen_underscore(self):
        assert is_valid_minion_id("Foo-bar_car") is True

    def test_with_dot(self):
        assert is_valid_minion_id("Foo.bar_car") is True

    def test_empty_string(self):
        assert is_valid_minion_id("") is False

    def test_with_space(self):
        assert is_valid_minion_id("Foo bar") is False

    def test_space_only(self):
        assert is_valid_minion_id(" ") is False

    def test_with_pipe(self):
        assert is_valid_minion_id("foo|bars") is False


class TestIsValidSettingId:
    def test_alphanumeric(self):
        assert is_valid_setting_id("foo") is True

    def test_with_hyphen(self):
        assert is_valid_setting_id("foo-bar") is True

    def test_mixed_case_hyphen_underscore(self):
        assert is_valid_setting_id("Foo-bar_car") is True

    def test_with_dot(self):
        assert is_valid_setting_id("Foo.bar_car") is True

    def test_with_dot_colon(self):
        assert is_valid_setting_id("Foo.bar.:car:") is True

    def test_with_slash_asterisk(self):
        assert is_valid_setting_id("Foo/bar*") is True

    def test_empty_string(self):
        assert is_valid_setting_id("") is False

    def test_with_space(self):
        assert is_valid_setting_id("Foo bar") is False

    def test_space_only(self):
        assert is_valid_setting_id(" ") is False

    def test_with_pipe(self):
        assert is_valid_setting_id("foo|bars") is False


class TestSupportsJinja:
    def test_duplicated_setting_supports_jinja(self):
        """Empty description implies duplicated setting; supports jinja."""
        setting = new_setting("id")
        assert setting.supports_jinja() is True

    def test_with_description_no_jinja(self):
        """Non-empty description + not jinja-escaped => no jinja."""
        setting = new_setting("id")
        setting.description = "foo"
        assert setting.supports_jinja() is False

    def test_with_description_jinja_escaped(self):
        """Non-empty description + jinja-escaped => supports jinja."""
        setting = new_setting("id")
        setting.description = "foo"
        setting.jinja_escaped = True
        assert setting.supports_jinja() is True

    def test_json_syntax_no_jinja(self):
        """JSON syntax => never supports jinja."""
        setting = new_setting("id")
        setting.description = "foo"
        setting.jinja_escaped = True
        setting.syntax = "json"
        assert setting.supports_jinja() is False
