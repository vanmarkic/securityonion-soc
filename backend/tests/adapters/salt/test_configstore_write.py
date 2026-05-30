"""Tests for SaltConfigstore.update_setting — the write path.

Anchored to server/modules/salt/saltstore_test.go TestUpdateSetting_*. We port
the SCALAR, STRUCTURAL, LIST and forcedType cases (Readonly, MissingSettingFile,
OverrideDefault, OverrideWithJinjaEscaped, FileWithJinja, AddGlobal, AddToNode,
DeleteGlobal, DeleteFromNode, DeleteAdvanced, UpdateGlobal, UpdateForNode,
UpdateAdvanced, UpdateFile, UpdateAdvancedFailToParse, AlignIntType,
FailToAlignIntType, AlignFloatType, FailToAlignFloatType, AlignBoolType,
FailToAlignBoolType, AlignNonStringType, AlignNonStringListType,
AlignBlankStringListType, AlignIntListType, FailToAlignIntListType,
AlignEmptyListIntType, ForceIntType, ForceListIntType, AlignFloatListType,
FailToAlignFloatListType, AlignEmptyListFloatType, AlignBoolListType,
FailToAlignBoolListType, AlignEmptyListBoolType, AlignListListType,
FailToAlignListListType, AlignEmptyListListType, AlignMapListType,
FailToAlignMapListType, AlignEmptyListMapType, ForceMapListFieldTypes_StringInput,
ForceMapListFieldTypes_NumericInput).

Each case rebuilds the Go fixture saltstack tree, runs update_setting, then
re-reads the affected setting via get_settings (the same way the Go test does)
and asserts on the resulting value. JSON parse-failure assertions use Python's
``json.loads`` error class (Go's exact json error strings are Go-specific).
"""

import json
from pathlib import Path

import pytest

from src.adapters.salt.configstore import SaltConfigstore, SaltStateError
from src.adapters.salt.relay import FakeRelayClient
from src.domain.config import Setting, new_setting

# Reuse the byte-for-byte Go fixture tree builder from the read-path tests.
from tests.adapters.salt.test_configstore import _build_full_fixture


def _store(tmp_path: Path) -> SaltConfigstore:
    _build_full_fixture(tmp_path)
    return SaltConfigstore(str(tmp_path))


def _find(settings: list[Setting], setting_id: str, node_id: str = "") -> Setting | None:
    for s in settings:
        if s.id == setting_id and s.node_id == node_id:
            return s
    return None


class TestReadonly:
    async def test_readonly_rejected(self, tmp_path: Path):
        store = _store(tmp_path)
        with pytest.raises(ValueError, match="Unable to modify or remove a readonly setting"):
            await store.update_setting(new_setting("myapp.ro"), remove=False)


class TestMissingSettingFile:
    async def test_missing_saltstack_dir_propagates(self, tmp_path: Path):
        # No fixture built: get_settings fails on the missing default dir,
        # mirroring Go's "lstat /default: no such file or directory".
        store = SaltConfigstore(str(tmp_path / "nope"))
        with pytest.raises(OSError):
            await store.update_setting(new_setting("some.setting"), remove=False)


class TestOverrideDefault:
    async def test_override_default_through_list_align(self, tmp_path: Path):
        # myapp.my_def's default is a list ("item1\nitem2\n"), so its absent
        # current value best-guesses to a list and align_type takes the []string
        # branch -> the value is split on \n (here a single line) and read back as
        # "new setting\n", matching Go's TestUpdateSetting_OverrideDefault.
        store = _store(tmp_path)
        setting = new_setting("myapp.my_def")
        setting.value = "new setting"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        new = _find(settings, "myapp.my_def")
        assert new is not None
        assert new.value == "new setting\n"


class TestOverrideWithJinjaEscaped:
    async def test_jinja_value_escaped_then_list_align(self, tmp_path: Path):
        # Same list-default routing as OverrideDefault. The jinja escaping runs
        # first and round-trips, and the []string align yields "<value>\n", per
        # Go's TestUpdateSetting_OverrideWithJinjaEscaped.
        store = _store(tmp_path)
        setting = new_setting("myapp.my_def")
        setting.value = "new setting {{foo}} {# comment #} {% multiline %}"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        new = _find(settings, "myapp.my_def")
        assert new is not None
        assert new.value == "new setting {{foo}} {# comment #} {% multiline %}\n"


class TestFileWithJinja:
    async def test_file_value_keeps_jinja_no_validation(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.foo__txt")
        setting.value = "new setting {{foo}} {# comment #} {% multiline %}"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        new = _find(settings, "myapp.foo__txt")
        assert new is not None
        # Files are not validated and not multiline-joined: value is verbatim.
        assert new.value == "new setting {{foo}} {# comment #} {% multiline %}"


class TestAddGlobal:
    async def test_add_global_setting(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.setting")
        setting.value = "new setting"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        assert len(settings) == 28 + 1
        new = _find(settings, "myapp.setting")
        assert new is not None
        assert new.value == "new setting"
        assert new.node_id == ""


class TestAddToNode:
    async def test_add_node_scoped_setting(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.setting")
        setting.value = "new setting"
        setting.node_id = "normal_import"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        assert len(settings) == 28 + 1
        new = _find(settings, "myapp.setting", "normal_import")
        assert new is not None
        assert new.value == "new setting"
        assert new.node_id == "normal_import"


class TestDeleteGlobal:
    async def test_delete_global_setting(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.str")
        await store.update_setting(setting, remove=True)

        settings = await store.get_settings(advanced=True)
        assert len(settings) == 28 - 1
        assert _find(settings, "myapp.str") is None


class TestDeleteFromNode:
    async def test_delete_node_setting(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.foo")
        setting.node_id = "normal_import"
        await store.update_setting(setting, remove=True)

        settings = await store.get_settings(advanced=True)
        assert len(settings) == 28 - 1
        assert _find(settings, "myapp.foo", "normal_import") is None


class TestDeleteAdvanced:
    async def test_delete_advanced_clears_value(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.advanced")
        await store.update_setting(setting, remove=True)

        settings = await store.get_settings(advanced=True)
        # Advanced write path ignores remove and writes the (empty) value.
        assert len(settings) == 28
        deleted = _find(settings, "myapp.advanced")
        assert deleted is not None
        assert deleted.value == ""


class TestUpdateGlobal:
    async def test_update_global_trims_value(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.str")
        setting.value = "new value\n"  # ensure trimmed
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        assert len(settings) == 28
        updated = _find(settings, "myapp.str")
        assert updated is not None
        assert updated.value == "new value"
        assert updated.node_id == ""


class TestUpdateForNode:
    async def test_update_node_setting(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.foo")
        setting.node_id = "normal_import"
        setting.value = "new value"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.foo", "normal_import")
        assert updated is not None
        assert updated.value == "new value"
        assert updated.node_id == "normal_import"


class TestUpdateAdvanced:
    async def test_update_advanced_raw_value(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.advanced")
        setting.value = "something: new"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.advanced")
        assert updated is not None
        assert updated.value == "something: new"
        assert updated.node_id == ""


class TestUpdateFile:
    async def test_update_then_delete_file(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.foo__txt")
        setting.file = True
        setting.value = "something"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.foo__txt")
        assert updated is not None
        assert updated.default == "anything"
        assert updated.value == "something"

        # Delete: the local file is removed, value falls back to the default.
        await store.update_setting(setting, remove=True)
        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.foo__txt")
        assert updated is not None
        assert updated.default == "anything"
        assert updated.value == "anything"


class TestUpdateAdvancedFailToParse:
    async def test_malformed_advanced_yaml_rejected(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.advanced")
        setting.value = "[s new advanced"
        setting.syntax = "yaml"
        with pytest.raises(ValueError, match=r"^ERROR_MALFORMED_YAML -> "):
            await store.update_setting(setting, remove=False)


class TestAlignIntType:
    async def test_align_int(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.int")
        setting.value = "44"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.int")
        assert updated is not None
        assert updated.value == "44"

    async def test_fail_to_align_int(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.int")
        setting.value = "not an int"
        with pytest.raises(ValueError, match=r'strconv\.ParseInt: parsing "not an int": invalid syntax'):
            await store.update_setting(setting, remove=False)


class TestAlignFloatType:
    async def test_align_float(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.float")
        setting.value = "44.2"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.float")
        assert updated is not None
        assert updated.value == "44.2"

    async def test_fail_to_align_float(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.float")
        setting.value = "not a float"
        with pytest.raises(ValueError, match=r'strconv\.ParseFloat: parsing "not a float": invalid syntax'):
            await store.update_setting(setting, remove=False)


class TestAlignBoolType:
    async def test_align_bool(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.bool")
        setting.value = "false"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.bool")
        assert updated is not None
        assert updated.value == "false"

    async def test_fail_to_align_bool(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.bool")
        setting.value = "not a bool"
        with pytest.raises(ValueError, match=r'strconv\.ParseBool: parsing "not a bool": invalid syntax'):
            await store.update_setting(setting, remove=False)


class TestAlignNonStringType:
    async def test_numeric_string_stays_string(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.str")
        setting.value = "123"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.str")
        assert updated is not None
        assert updated.value == "123"


class TestAlignBlankStringListType:
    async def test_empty_string_list_align(self, tmp_path: Path):
        # Port of Go TestUpdateSetting_AlignBlankStringListType: an empty-list
        # default best-guesses the new value as a list.
        store = _store(tmp_path)

        # Default should be an empty list.
        settings = await store.get_settings(advanced=True)
        original = _find(settings, "myapp.empty_lists.list_str")
        assert original is not None
        assert original.value == ""

        # Update empty setting with a non-blank value -> "foo\n".
        setting = new_setting("myapp.empty_lists.list_str")
        setting.value = "foo"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.empty_lists.list_str")
        assert updated is not None
        assert updated.value == "foo\n"

        # Update with an empty-lines value ("\n") -> back to an empty list.
        setting = new_setting("myapp.empty_lists.list_str")
        setting.value = "\n"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.empty_lists.list_str")
        assert updated is not None
        assert updated.value == ""


# ---------------------------------------------------------------------------
# LIST type alignment (existing list values -> dispatch on first element).
# ---------------------------------------------------------------------------


class TestAlignIntListType:
    async def test_align_int_list(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_int")
        setting.value = "44\n2\n1"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.lists.list_int")
        assert updated is not None
        assert updated.value == "44\n2\n1\n"

    async def test_fail_to_align_int_list(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_int")
        setting.value = "1\n2\ninvalid"
        with pytest.raises(ValueError, match=r'strconv\.ParseInt: parsing "invalid": invalid syntax'):
            await store.update_setting(setting, remove=False)


class TestAlignEmptyListIntType:
    async def test_prime_then_update_then_fail(self, tmp_path: Path):
        store = _store(tmp_path)

        # Prime the empty list with ints.
        setting = new_setting("myapp.empty_lists.list_int")
        setting.value = "123\n456"
        await store.update_setting(setting, remove=False)

        # Update with more ints.
        setting = new_setting("myapp.empty_lists.list_int")
        setting.value = "123\n456\n23"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.empty_lists.list_int")
        assert updated is not None
        assert updated.value == "123\n456\n23\n"

        # Wrong type now fails (the list is primed with ints).
        setting = new_setting("myapp.empty_lists.list_int")
        setting.value = "cannot set string on int list"
        with pytest.raises(
            ValueError,
            match=r'strconv\.ParseInt: parsing "cannot set string on int list": invalid syntax',
        ):
            await store.update_setting(setting, remove=False)


class TestForceIntType:
    async def test_force_int(self, tmp_path: Path):
        # myapp.int_nodefault has forcedType "int" and no default.
        store = _store(tmp_path)
        setting = new_setting("myapp.int_nodefault")
        setting.value = "44"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.int_nodefault")
        assert updated is not None
        assert updated.value == "44"


class TestForceListIntType:
    async def test_force_int_list(self, tmp_path: Path):
        # myapp.int_list_nodefault has forcedType "[]int" and no default.
        store = _store(tmp_path)
        setting = new_setting("myapp.int_list_nodefault")
        setting.value = "44\n55"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.int_list_nodefault")
        assert updated is not None
        assert updated.value == "44\n55\n"


class TestAlignFloatListType:
    async def test_align_float_list(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_float")
        setting.value = "44.3\n2.1\n1.2"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.lists.list_float")
        assert updated is not None
        assert updated.value == "44.3\n2.1\n1.2\n"

    async def test_fail_to_align_float_list(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_float")
        setting.value = "1.2\nnope"
        with pytest.raises(ValueError, match=r'strconv\.ParseFloat: parsing "nope": invalid syntax'):
            await store.update_setting(setting, remove=False)


class TestAlignEmptyListFloatType:
    async def test_prime_then_update_then_fail(self, tmp_path: Path):
        store = _store(tmp_path)

        setting = new_setting("myapp.empty_lists.list_float")
        setting.value = "1.23\n4.56"
        await store.update_setting(setting, remove=False)

        setting = new_setting("myapp.empty_lists.list_float")
        setting.value = "1.23\n4.56\n2.3"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.empty_lists.list_float")
        assert updated is not None
        assert updated.value == "1.23\n4.56\n2.3\n"

        setting = new_setting("myapp.empty_lists.list_float")
        setting.value = "cannot set string on float list"
        with pytest.raises(
            ValueError,
            match=r'strconv\.ParseFloat: parsing "cannot set string on float list": invalid syntax',
        ):
            await store.update_setting(setting, remove=False)


class TestAlignBoolListType:
    async def test_align_bool_list(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_bool")
        setting.value = "true\nfalse\ntrue"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.lists.list_bool")
        assert updated is not None
        assert updated.value == "true\nfalse\ntrue\n"

    async def test_fail_to_align_bool_list(self, tmp_path: Path):
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_bool")
        setting.value = "true\nfalse\nhi"
        with pytest.raises(ValueError, match=r'strconv\.ParseBool: parsing "hi": invalid syntax'):
            await store.update_setting(setting, remove=False)


class TestAlignEmptyListBoolType:
    async def test_prime_then_update_then_fail(self, tmp_path: Path):
        store = _store(tmp_path)

        setting = new_setting("myapp.empty_lists.list_bool")
        setting.value = "true\nfalse"
        await store.update_setting(setting, remove=False)

        setting = new_setting("myapp.empty_lists.list_bool")
        setting.value = "true\ntrue\nfalse"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.empty_lists.list_bool")
        assert updated is not None
        assert updated.value == "true\ntrue\nfalse\n"

        setting = new_setting("myapp.empty_lists.list_bool")
        setting.value = "cannot set string on bool list"
        with pytest.raises(
            ValueError,
            match=r'strconv\.ParseBool: parsing "cannot set string on bool list": invalid syntax',
        ):
            await store.update_setting(setting, remove=False)


class TestAlignListListType:
    async def test_align_list_list(self, tmp_path: Path):
        store = _store(tmp_path)
        expected = '["item1","item2"]\n["item3","item3"]\n["item5","item6"]\n'
        setting = new_setting("myapp.lists.list_list_str")
        setting.value = expected
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.lists.list_list_str")
        assert updated is not None
        assert updated.value == expected

    async def test_fail_to_align_list_list(self, tmp_path: Path):
        # Can't change a list-of-lists to a list of bools (a bool isn't a list).
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_list_str")
        setting.value = "true\nfalse"
        with pytest.raises(ValueError):
            await store.update_setting(setting, remove=False)


class TestAlignEmptyListListType:
    async def test_prime_then_update_then_fail(self, tmp_path: Path):
        store = _store(tmp_path)

        setting = new_setting("myapp.empty_lists.list_list_str")
        setting.value = '["item1","item2"]\n["item3","item3"]'
        await store.update_setting(setting, remove=False)

        expected = '["item1","item2"]\n["item3","item3"]\n["item5","item6"]\n'
        setting = new_setting("myapp.empty_lists.list_list_str")
        setting.value = expected
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.empty_lists.list_list_str")
        assert updated is not None
        assert updated.value == expected

        # Malformed JSON line -> json.loads raises.
        setting = new_setting("myapp.empty_lists.list_list_str")
        setting.value = "cannot set list of strings\non list of lists"
        with pytest.raises(json.JSONDecodeError):
            await store.update_setting(setting, remove=False)


class TestAlignMapListType:
    async def test_align_map_list(self, tmp_path: Path):
        store = _store(tmp_path)
        expected = (
            '{"key1":"value1","key2":"value2"}\n'
            '{"key1":"value3","key2":"value4"}\n'
            '{"key1":"value5","key2":"value6"}\n'
        )
        setting = new_setting("myapp.lists.list_map_str")
        setting.value = expected
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.lists.list_map_str")
        assert updated is not None
        assert updated.value == expected

    async def test_fail_to_align_map_list(self, tmp_path: Path):
        # Can't change a list-of-maps to a list of bools (a bool isn't a map).
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_map_str")
        setting.value = "true\nfalse"
        with pytest.raises(ValueError):
            await store.update_setting(setting, remove=False)


class TestAlignEmptyListMapType:
    async def test_prime_then_update_then_fail(self, tmp_path: Path):
        store = _store(tmp_path)

        setting = new_setting("myapp.empty_lists.list_map_str")
        setting.value = '{"key1":"value1","key2":"value2"}'
        await store.update_setting(setting, remove=False)

        expected = (
            '{"key1":"value1","key2":"value2"}\n'
            '{"key1":"value3","key2":"value4"}\n'
        )
        setting = new_setting("myapp.empty_lists.list_map_str")
        setting.value = expected
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.empty_lists.list_map_str")
        assert updated is not None
        assert updated.value == expected

        setting = new_setting("myapp.empty_lists.list_map_str")
        setting.value = "cannot set list of strings\non list of maps"
        with pytest.raises(json.JSONDecodeError):
            await store.update_setting(setting, remove=False)


class TestAlignNonStringListType:
    async def test_string_list_keeps_strings(self, tmp_path: Path):
        # myapp.lists.list_str holds strings, so numeric input stays strings.
        store = _store(tmp_path)
        setting = new_setting("myapp.lists.list_str")
        setting.value = "123\n456"
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.lists.list_str")
        assert updated is not None
        assert updated.value == "123\n456\n"


# ---------------------------------------------------------------------------
# forcedType "[]{}" with typed UI elements (coerce_map_list_field_types).
# ---------------------------------------------------------------------------


class TestForceMapListFieldTypes:
    async def test_string_input_coerced_to_typed_json(self, tmp_path: Path):
        # The UI sends int/bool fields as strings inside JSON objects; coercion
        # re-types port -> int and enabled -> bool (myapp.ui_map_typed).
        store = _store(tmp_path)
        setting = new_setting("myapp.ui_map_typed")
        setting.value = (
            '{"enabled":"true","name":"alpha","port":"8080"}\n'
            '{"enabled":"false","name":"beta","port":"9090"}'
        )
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.ui_map_typed")
        assert updated is not None
        assert updated.value == (
            '{"enabled":true,"name":"alpha","port":8080}\n'
            '{"enabled":false,"name":"beta","port":9090}\n'
        )

    async def test_numeric_input_float_coerced_to_int(self, tmp_path: Path):
        # Properly-typed JSON: a JSON-parsed float 8080.0 must coerce to int 8080.
        store = _store(tmp_path)
        setting = new_setting("myapp.ui_map_typed")
        setting.value = '{"enabled":true,"name":"alpha","port":8080}'
        await store.update_setting(setting, remove=False)

        settings = await store.get_settings(advanced=True)
        updated = _find(settings, "myapp.ui_map_typed")
        assert updated is not None
        assert updated.value == '{"enabled":true,"name":"alpha","port":8080}\n'


# ---------------------------------------------------------------------------
# sync_settings / sync_module — the relay seam.
# ---------------------------------------------------------------------------


class TestSyncSettings:
    async def test_relays_highstate_args(self, tmp_path: Path):
        relay = FakeRelayClient({"manage-salt": "true"})
        store = SaltConfigstore(str(tmp_path), relay=relay, request_id="req")
        await store.sync_settings()

        assert len(relay.calls) == 1
        command_id, args = relay.calls[0]
        assert command_id == "req_manage-salt"
        assert args == {
            "command": "manage-salt",
            "operation": "highstate",
            "minion": "*",
        }

    async def test_false_raises_salt_state(self, tmp_path: Path):
        relay = FakeRelayClient({"manage-salt": "false"})
        store = SaltConfigstore(str(tmp_path), relay=relay)
        with pytest.raises(SaltStateError, match="ERROR_SALT_STATE"):
            await store.sync_settings()

    async def test_no_relay_raises(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(RuntimeError, match="no relay configured"):
            await store.sync_settings()


class TestSyncModule:
    async def test_relays_state_args_without_async(self, tmp_path: Path):
        relay = FakeRelayClient({"manage-salt": "true"})
        store = SaltConfigstore(str(tmp_path), relay=relay, request_id="req")
        await store.sync_module("idstools", force=False)

        command_id, args = relay.calls[0]
        assert command_id == "req_manage-salt"
        assert args == {
            "command": "manage-salt",
            "operation": "state",
            "state": "idstools",
        }

    async def test_force_maps_to_async_true(self, tmp_path: Path):
        relay = FakeRelayClient({"manage-salt": "true"})
        store = SaltConfigstore(str(tmp_path), relay=relay)
        await store.sync_module("idstools", force=True)

        _command_id, args = relay.calls[0]
        assert args == {
            "command": "manage-salt",
            "operation": "state",
            "state": "idstools",
            "async": "true",
        }

    async def test_error_code_passthrough(self, tmp_path: Path):
        # An output matching ^ERROR_[A-Z_]+$ is raised verbatim.
        relay = FakeRelayClient({"manage-salt": "ERROR_FAILED_SALT_VALIDATION"})
        store = SaltConfigstore(str(tmp_path), relay=relay)
        with pytest.raises(SaltStateError, match="^ERROR_FAILED_SALT_VALIDATION$"):
            await store.sync_module("idstools", force=False)

    async def test_false_raises_salt_state(self, tmp_path: Path):
        relay = FakeRelayClient({"manage-salt": "false"})
        store = SaltConfigstore(str(tmp_path), relay=relay)
        with pytest.raises(SaltStateError, match="^ERROR_SALT_STATE$"):
            await store.sync_module("idstools", force=False)

    async def test_no_relay_raises(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(RuntimeError, match="no relay configured"):
            await store.sync_module("idstools", force=False)
