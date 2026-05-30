"""Unit tests for the Salt settings parsing helpers.

These cover the building blocks ported from saltstore.go:
recursively_parse_settings, parse_yaml, convert_to_json, post_process,
filter_settings, and sort_settings.
"""

from pathlib import Path

from src.adapters.salt.settings import (
    convert_to_json,
    filter_settings,
    parse_yaml,
    post_process,
    recursively_parse_settings,
    render_scalar,
    sort_settings,
)
from src.domain.config import Setting, new_setting


def _by_id(settings: list[Setting]) -> dict[str, Setting]:
    return {s.id: s for s in settings}


class TestRenderScalar:
    def test_bool_renders_go_lowercase(self):
        # Go fmt.Sprintf("%v", true/false) prints lowercase true/false.
        assert render_scalar(True) == "true"
        assert render_scalar(False) == "false"

    def test_none_renders_go_nil(self):
        # Go fmt.Sprintf("%v", nil) prints <nil>; pyyaml decodes empty as None.
        assert render_scalar(None) == "<nil>"

    def test_int_and_float_and_str(self):
        assert render_scalar(123) == "123"
        assert render_scalar(3.5) == "3.5"
        assert render_scalar("hello") == "hello"


class TestConvertToJson:
    def test_list_uses_compact_separators(self):
        assert convert_to_json(["item1", "item2"]) == '["item1","item2"]'

    def test_map_sorts_keys_and_is_compact(self):
        # Go encoding/json sorts map keys and emits no spaces.
        assert convert_to_json({"key2": "value2", "key1": "value1"}) == (
            '{"key1":"value1","key2":"value2"}'
        )


class TestParseYaml:
    def test_loads_mapping(self, tmp_path: Path):
        f = tmp_path / "defaults.yaml"
        f.write_text("myapp:\n  zdef: vanilla\n")
        assert parse_yaml(str(f)) == {"myapp": {"zdef": "vanilla"}}


class TestRecursivelyParseSettings:
    def test_nested_map_becomes_dotted_id(self):
        mapped = {"myapp": {"str": "my_str"}}
        out = recursively_parse_settings([], mapped, "", "", False)
        ids = _by_id(out)
        assert "myapp.str" in ids
        assert ids["myapp.str"].value == "my_str"
        assert ids["myapp.str"].multiline is False

    def test_list_becomes_multiline_joined_value(self):
        mapped = {"myapp": {"my_def": ["item1", "item2"]}}
        out = recursively_parse_settings([], mapped, "", "", False)
        setting = _by_id(out)["myapp.my_def"]
        assert setting.value == "item1\nitem2\n"
        assert setting.multiline is True

    def test_list_of_list_and_map_items_are_json(self):
        mapped = {
            "x": {
                "list_list_str": [["item1", "item2"], ["item3", "item4"]],
                "list_map_str": [
                    {"key1": "value1", "key2": "value2"},
                    {"key1": "value3", "key2": "value4"},
                ],
            }
        }
        out = recursively_parse_settings([], mapped, "", "", False)
        ids = _by_id(out)
        assert ids["x.list_list_str"].value == '["item1","item2"]\n["item3","item4"]\n'
        assert ids["x.list_map_str"].value == (
            '{"key1":"value1","key2":"value2"}\n{"key1":"value3","key2":"value4"}\n'
        )

    def test_empty_list_yields_empty_value(self):
        mapped = {"x": {"empty": []}}
        out = recursively_parse_settings([], mapped, "", "", False)
        setting = _by_id(out)["x.empty"]
        assert setting.value == ""
        assert setting.multiline is True

    def test_empty_string_items_are_skipped(self):
        mapped = {"x": {"items": ["", "keep", ""]}}
        out = recursively_parse_settings([], mapped, "", "", False)
        assert _by_id(out)["x.items"].value == "keep\n"

    def test_scalar_types_render_like_go(self):
        mapped = {
            "myapp": {
                "int": 123,
                "float": 3.5,
                "bool": True,
                "str": "my_str",
            }
        }
        out = recursively_parse_settings([], mapped, "", "", False)
        ids = _by_id(out)
        assert ids["myapp.int"].value == "123"
        assert ids["myapp.float"].value == "3.5"
        assert ids["myapp.bool"].value == "true"
        assert ids["myapp.str"].value == "my_str"

    def test_merge_existing_global_overwrites_value(self):
        existing = new_setting("myapp.zdef")
        existing.value = "vanilla"
        existing.node_id = ""
        # merge=True, minion="" -> overwrite the existing global setting in place.
        out = recursively_parse_settings(
            [existing], {"myapp": {"zdef": "chocolate"}}, "", "", True
        )
        # No new setting appended; the existing one is overwritten.
        zdefs = [s for s in out if s.id == "myapp.zdef"]
        assert len(zdefs) == 1
        assert zdefs[0].value == "chocolate"
        assert zdefs[0].node_id == ""

    def test_merge_reconciles_multiline_conflict(self):
        existing = new_setting("myapp.v")
        existing.value = "scalar"
        existing.multiline = False
        out = recursively_parse_settings(
            [existing], {"myapp": {"v": ["a", "b"]}}, "", "", True
        )
        merged = _by_id(out)["myapp.v"]
        assert merged.value == "a\nb\n"
        assert merged.multiline is True

    def test_minion_appends_new_node_setting(self):
        existing = new_setting("myapp.foo")
        existing.value = "default-val"
        existing.node_id = ""
        out = recursively_parse_settings(
            [existing], {"myapp": {"foo": "minion-born"}}, "", "node1", True
        )
        # The global one is untouched; a node-scoped setting is appended.
        foos = sorted((s for s in out if s.id == "myapp.foo"), key=lambda s: s.node_id)
        assert len(foos) == 2
        assert foos[0].node_id == "" and foos[0].value == "default-val"
        assert foos[1].node_id == "node1" and foos[1].value == "minion-born"

    def test_no_merge_appends_when_global_absent(self):
        # merge default path: minion="", no existing -> append new global setting.
        out = recursively_parse_settings([], {"myapp": {"foo": "v"}}, "", "", False)
        setting = _by_id(out)["myapp.foo"]
        assert setting.node_id == ""
        assert setting.value == "v"


class TestPostProcess:
    def test_empty_description_marks_advanced(self):
        s = new_setting("a")
        s.description = ""
        post_process([s])
        assert s.advanced is True

    def test_described_setting_stays_non_advanced(self):
        s = new_setting("a")
        s.description = "has description"
        post_process([s])
        assert s.advanced is False

    def test_jinja_supporting_value_is_unescaped(self):
        # A descriptionless (duplicated) setting supports jinja; value unescaped.
        s = new_setting("a")
        s.description = ""
        s.value = "[SO_JINJA_SL_START] x [SO_JINJA_SL_END]"
        post_process([s])
        assert s.value == "{{ x }}"

    def test_json_syntax_value_not_unescaped(self):
        s = new_setting("a")
        s.description = ""
        s.syntax = "json"
        s.value = "[SO_JINJA_SL_START] x [SO_JINJA_SL_END]"
        post_process([s])
        # json syntax does not support jinja, so the value is left intact.
        assert s.value == "[SO_JINJA_SL_START] x [SO_JINJA_SL_END]"


class TestFilterSettings:
    def test_advanced_true_returns_everything(self):
        s1 = new_setting("a")
        s2 = new_setting("b")
        s2.advanced = True
        out = filter_settings([s1, s2], True)
        assert out == [s1, s2]

    def test_advanced_false_drops_advanced(self):
        s1 = new_setting("a")
        s2 = new_setting("b")
        s2.advanced = True
        out = filter_settings([s1, s2], False)
        assert out == [s1]


class TestSortSettings:
    def test_orders_by_id_with_advanced_last(self):
        # Go comparator pushes ids ending in "advanced" toward the end.
        c = new_setting("myapp.zdef")
        a = new_setting("myapp.advanced")
        b = new_setting("myapp.bar")
        out = sort_settings([c, a, b])
        ids = [s.id for s in out]
        assert ids[-1] == "myapp.advanced"
        # Non-advanced ids keep ascending order relative to each other.
        assert ids.index("myapp.bar") < ids.index("myapp.zdef")
