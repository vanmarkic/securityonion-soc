"""Tests for SaltConfigstore.update_setting — the write path.

Anchored to server/modules/salt/saltstore_test.go TestUpdateSetting_*. We port
the SCALAR and STRUCTURAL cases (Readonly, MissingSettingFile, OverrideDefault,
OverrideWithJinjaEscaped, FileWithJinja, AddGlobal, AddToNode, DeleteGlobal,
DeleteFromNode, DeleteAdvanced, UpdateGlobal, UpdateForNode, UpdateAdvanced,
UpdateFile, UpdateAdvancedFailToParse, AlignIntType, FailToAlignIntType,
AlignFloatType, FailToAlignFloatType, AlignBoolType, FailToAlignBoolType,
AlignNonStringType, AlignBlankStringListType).

Each case rebuilds the Go fixture saltstack tree, runs update_setting, then
re-reads the affected setting via get_settings (the same way the Go test does)
and asserts on the resulting value. The LIST/forcedType cases (AlignIntListType,
ForceIntType, etc.) belong to the next unit (B2) and are NOT ported here.
"""

from pathlib import Path

import pytest

from src.adapters.salt.configstore import SaltConfigstore
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
    async def test_override_default_routes_through_list_align_b2(self, tmp_path: Path):
        # myapp.my_def's default is a list ("item1\nitem2\n"), so its absent
        # current value best-guesses to a list and align_type takes the []string
        # branch -> deferred to B2. (Go expects "new setting\n" once B2 lands.)
        store = _store(tmp_path)
        setting = new_setting("myapp.my_def")
        setting.value = "new setting"
        with pytest.raises(NotImplementedError, match="B2"):
            await store.update_setting(setting, remove=False)


class TestOverrideWithJinjaEscaped:
    async def test_jinja_value_escaped_before_b2_list_align(self, tmp_path: Path):
        # Same list-default routing as OverrideDefault. The jinja escaping still
        # runs first (and would round-trip), but the []string align is B2.
        store = _store(tmp_path)
        setting = new_setting("myapp.my_def")
        setting.value = "new setting {{foo}} {# comment #} {% multiline %}"
        with pytest.raises(NotImplementedError, match="B2"):
            await store.update_setting(setting, remove=False)


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
    async def test_empty_string_list_align_deferred_to_b2(self, tmp_path: Path):
        # myapp.empty_lists.list_str is [] (a list) in the fixture, so updating it
        # routes through align_type's list branch -> deferred to B2.
        store = _store(tmp_path)
        setting = new_setting("myapp.empty_lists.list_str")
        setting.value = "foo"
        with pytest.raises(NotImplementedError, match="B2"):
            await store.update_setting(setting, remove=False)
