"""Unit tests for the Salt settings parsing helpers.

These cover the building blocks ported from saltstore.go:
recursively_parse_settings, parse_yaml, convert_to_json, post_process,
filter_settings, and sort_settings.
"""

from pathlib import Path

import pytest

from src.adapters.salt.settings import (
    cast_to_string_array,
    convert_to_json,
    filter_settings,
    parse_advanced,
    parse_yaml,
    post_process,
    read_file,
    recursively_parse_annotations,
    recursively_parse_settings,
    rel_path_from_id,
    render_scalar,
    sort_settings,
    update_setting_with_annotation,
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


class TestCastToStringArray:
    def test_casts_list_of_strings(self):
        assert cast_to_string_array(["a", "b", "c"]) == ["a", "b", "c"]

    def test_empty_list_yields_empty(self):
        assert cast_to_string_array([]) == []

    def test_non_list_raises(self):
        # Go asserts value.([]interface{}); a non-list panics. We raise instead.
        with pytest.raises(TypeError):
            cast_to_string_array("not-a-list")

    def test_non_string_item_raises(self):
        # Go asserts tmp.(string) on each item.
        with pytest.raises(TypeError):
            cast_to_string_array(["ok", 5])


class TestUpdateSettingWithAnnotation:
    def test_string_keys_use_go_percent_v(self):
        s = new_setting("x")
        update_setting_with_annotation(
            s,
            {
                "title": "My Title",
                "description": "desc",
                "regex": "^a$",
                "regexFailureMessage": "nope",
                "helpLink": "page",
                "syntax": "yaml",
                "forcedType": "[]int",
            },
        )
        assert s.title == "My Title"
        assert s.description == "desc"
        assert s.regex == "^a$"
        assert s.regex_failure_message == "nope"
        assert s.help_link == "page"
        assert s.syntax == "yaml"
        assert s.forced_type == "[]int"

    def test_bool_keys(self):
        s = new_setting("x")
        update_setting_with_annotation(
            s,
            {
                "readonly": True,
                "readonlyUi": True,
                "global": True,
                "multiline": True,
                "node": True,
                "sensitive": True,
                "advanced": True,
                "duplicates": True,
                "jinjaEscaped": True,
                "required": True,
            },
        )
        assert s.readonly is True
        assert s.readonly_ui is True
        assert s.global_ is True
        assert s.multiline is True
        assert s.node is True
        assert s.sensitive is True
        assert s.advanced is True
        assert s.duplicates is True
        assert s.jinja_escaped is True
        assert s.required is True

    def test_options_and_separator(self):
        s = new_setting("x")
        update_setting_with_annotation(
            s, {"options": ["one", "two"], "optionSeparator": ","}
        )
        assert s.options == ["one", "two"]
        assert s.option_separator == ","

    def test_ui_elements_built_with_inner_switch(self):
        s = new_setting("x")
        update_setting_with_annotation(
            s,
            {
                "uiElements": [
                    {
                        "field": "something",
                        "label": "something nice",
                        "forcedType": "bool",
                        "multiline": False,
                        "default": True,
                        "required": False,
                        "readonly": True,
                    },
                    {
                        "field": "another",
                        "label": "another thing",
                        "forcedType": "[]string",
                        "options": ["blue", "red"],
                        "default": "red",
                    },
                ],
                "uiElementsDeleteMessage": "are you sure?",
            },
        )
        assert len(s.ui_elements) == 2
        first = s.ui_elements[0]
        assert first.field == "something"
        assert first.label == "something nice"
        assert first.forced_type == "bool"
        assert first.readonly is True
        assert first.default is True
        second = s.ui_elements[1]
        assert second.options == ["blue", "red"]
        assert second.default == "red"
        assert s.ui_elements_delete_message == "are you sure?"

    def test_ui_elements_non_map_item_skipped(self):
        s = new_setting("x")
        update_setting_with_annotation(s, {"uiElements": ["not-a-map", {"field": "ok"}]})
        assert len(s.ui_elements) == 1
        assert s.ui_elements[0].field == "ok"

    def test_unknown_keys_ignored(self):
        s = new_setting("x")
        update_setting_with_annotation(s, {"bogus": "value", "title": "kept"})
        assert s.title == "kept"

    def test_file_annotation_reads_default_and_local(self, tmp_path: Path):
        # relPathFromId("myapp.foo__txt") -> myapp/foo.txt
        (tmp_path / "default" / "salt" / "myapp").mkdir(parents=True)
        (tmp_path / "local" / "salt" / "myapp").mkdir(parents=True)
        (tmp_path / "default" / "salt" / "myapp" / "foo.txt").write_text("anything")
        (tmp_path / "local" / "salt" / "myapp" / "foo.txt").write_text("old")

        s = new_setting("myapp.foo__txt")
        update_setting_with_annotation(s, {"file": True}, saltstack_dir=str(tmp_path))
        assert s.file is True
        assert s.multiline is True
        assert s.default == "anything"
        assert s.default_available is True
        assert s.value == "old"

    def test_file_annotation_value_falls_back_to_default(self, tmp_path: Path):
        (tmp_path / "default" / "salt" / "myapp").mkdir(parents=True)
        (tmp_path / "default" / "salt" / "myapp" / "foo.txt").write_text("anything")
        # No local file; value should fall back to the default contents.
        s = new_setting("myapp.foo__txt")
        update_setting_with_annotation(s, {"file": True}, saltstack_dir=str(tmp_path))
        assert s.value == "anything"


class TestRecursivelyParseAnnotations:
    def test_end_of_branch_detection_attaches_to_existing(self):
        # A node with a non-dict child is an end-of-branch; its annotations apply
        # to the existing same-id setting.
        existing = new_setting("myapp.int")
        existing.value = "123"
        out, found = recursively_parse_annotations(
            [existing], {"myapp": {"int": {"description": "d", "global": True}}}, ""
        )
        assert found is False  # top level had only a dict child
        target = next(s for s in out if s.id == "myapp.int")
        assert target.description == "d"
        assert target.global_ is True
        # No annotation-only setting created for the grouping node "myapp".
        assert not any(s.id == "myapp" for s in out)

    def test_annotation_only_setting_is_created(self):
        out, _ = recursively_parse_annotations(
            [], {"myapp": {"newkey": {"description": "brand new"}}}, ""
        )
        created = next(s for s in out if s.id == "myapp.newkey")
        assert created.description == "brand new"

    def test_grouping_node_is_not_end_of_branch(self):
        # "myapp" only has dict children, so it must not become a setting.
        out, _ = recursively_parse_annotations(
            [], {"myapp": {"a": {"title": "A"}, "b": {"title": "B"}}}, ""
        )
        ids = {s.id for s in out}
        assert ids == {"myapp.a", "myapp.b"}

    def test_found_annotation_true_when_non_dict_child(self):
        # A level holding a non-dict value reports found_annotation True upward.
        _out, found = recursively_parse_annotations([], {"title": "leaf"}, "")
        assert found is True

    def test_sensitive_masks_value_and_clears_default(self):
        existing = new_setting("myapp.secret")
        existing.value = "supersecret"
        existing.default = "supersecret"
        out, _ = recursively_parse_annotations(
            [existing], {"myapp": {"secret": {"sensitive": True}}}, ""
        )
        masked = next(s for s in out if s.id == "myapp.secret")
        assert masked.value == "******"
        assert masked.default == ""

    def test_applies_to_all_matching_existing_settings(self):
        # Both a global and a node-scoped setting share the id; annotations apply
        # to each (Go iterates all settings, not just the first match).
        g = new_setting("myapp.foo")
        n = new_setting("myapp.foo")
        n.node_id = "node1"
        out, _ = recursively_parse_annotations(
            [g, n], {"myapp": {"foo": {"description": "shared"}}}, ""
        )
        assert all(s.description == "shared" for s in out if s.id == "myapp.foo")


class TestParseAdvanced:
    def test_global_advanced_setting(self, tmp_path: Path):
        f = tmp_path / "adv.sls"
        f.write_text("myapp:\n  global: advanced\n")
        out = parse_advanced(str(f), [], "", "myapp.advanced")
        s = next(x for x in out if x.id == "myapp.advanced")
        assert s.value == "myapp:\n  global: advanced\n"
        assert s.global_ is True
        assert s.node is False
        assert s.node_id == ""
        assert s.multiline is True
        assert s.syntax == "yaml"

    def test_node_advanced_setting(self, tmp_path: Path):
        f = tmp_path / "adv.sls"
        f.write_text("content\n")
        out = parse_advanced(str(f), [], "node1", "advanced")
        s = next(x for x in out if x.id == "advanced")
        assert s.global_ is False
        assert s.node is True
        assert s.node_id == "node1"

    def test_missing_file_is_swallowed(self, tmp_path: Path):
        out = parse_advanced(str(tmp_path / "missing.sls"), [], "", "advanced")
        assert out == []


class TestRelPathFromId:
    @pytest.mark.parametrize(
        ("setting_id", "expected"),
        [
            # Double underscore -> dot (the file-annotation case).
            ("myapp.foo__txt", "myapp/foo.txt"),
            ("soc.files.soc.banner__md", "soc/files/soc/banner.md"),
            # Plain dotted id: dots -> slashes, single underscore untouched.
            ("myapp.int", "myapp/int"),
            ("a_b.c_d", "a_b/c_d"),
            # The "..".->"____" shenanigan branch: four underscores become "__"
            # ->"__" (i.e. "..") after step 2, then ".."->"____" restores them.
            ("myapp____txt", "myapp____txt"),
            ("a__b__c", "a.b.c"),
        ],
    )
    def test_matches_go_rel_path_from_id(self, setting_id: str, expected: str):
        # Verified byte-for-byte against server/modules/salt/saltstore.go:565-572.
        assert rel_path_from_id(setting_id) == expected


class TestReadFile:
    def test_reads_contents(self, tmp_path: Path):
        f = tmp_path / "f.txt"
        f.write_text("hello")
        assert read_file(str(f)) == "hello"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(OSError):
            read_file(str(tmp_path / "nope.txt"))
