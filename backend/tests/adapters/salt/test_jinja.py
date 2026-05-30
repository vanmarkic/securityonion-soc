"""Tests for the Jinja escape/unescape seam — ported from syntax/jinja.go."""

from src.adapters.salt.jinja import escape_jinja, unescape_jinja


class TestEscapeJinja:
    def test_replaces_all_token_pairs(self):
        value = "{{ a }} {# b #} {% c %}"
        escaped = escape_jinja(value)
        assert escaped == (
            "[SO_JINJA_SL_START] a [SO_JINJA_SL_END] "
            "[SO_JINJA_CM_START] b [SO_JINJA_CM_END] "
            "[SO_JINJA_ML_START] c [SO_JINJA_ML_END]"
        )

    def test_no_jinja_is_unchanged(self):
        assert escape_jinja("plain text") == "plain text"


class TestUnescapeJinja:
    def test_replaces_all_token_pairs(self):
        value = (
            "[SO_JINJA_SL_START] a [SO_JINJA_SL_END] "
            "[SO_JINJA_CM_START] b [SO_JINJA_CM_END] "
            "[SO_JINJA_ML_START] c [SO_JINJA_ML_END]"
        )
        assert unescape_jinja(value) == "{{ a }} {# b #} {% c %}"

    def test_no_token_is_unchanged(self):
        assert unescape_jinja("plain text") == "plain text"


class TestRoundTrip:
    def test_escape_then_unescape_restores_original(self):
        original = "{{ pillar['x'] }} {# note #} {% if y %}z{% endif %}"
        assert unescape_jinja(escape_jinja(original)) == original
