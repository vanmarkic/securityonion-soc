"""Tests for SaltConfigstore.get_settings — DEFAULTS tier only.

Anchored to server/modules/salt/saltstore_test.go TestGetSettings. The Go test
mixes defaults, local-pillar overrides, and static annotations; this unit only
implements the defaults walk, so we reproduce the exact defaults.yaml fixture
(test_resources/saltstack/default/salt/myapp/defaults.yaml) and assert only the
defaults-derived settings: myapp.my_def and myapp.zdef, both with
default == value and default_available == True.
"""

from pathlib import Path

import pytest

from src.adapters.salt.configstore import SaltConfigstore
from src.domain.config import Setting
from src.ports.config import Configstore

# Byte-for-byte the Go fixture at
# test_resources/saltstack/default/salt/myapp/defaults.yaml.
DEFAULTS_YAML = "myapp:\n  my_def:\n  - item1\n  - item2\n  zdef: vanilla\n"


def _write_defaults(saltstack_dir: Path, relative: str, content: str) -> None:
    target = saltstack_dir / "default" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _by_id(settings: list[Setting]) -> dict[str, Setting]:
    return {s.id: s for s in settings}


class TestSaltConfigstoreProtocol:
    def test_satisfies_configstore_protocol(self, tmp_path: Path):
        assert isinstance(SaltConfigstore(str(tmp_path)), Configstore)

    def test_strips_trailing_slash_from_dir(self):
        store = SaltConfigstore("/opt/so/saltstack/")
        assert store.saltstack_dir == "/opt/so/saltstack"


class TestGetSettingsDefaults:
    async def test_parses_defaults_fixture_like_go(self, tmp_path: Path):
        _write_defaults(tmp_path, "salt/myapp/defaults.yaml", DEFAULTS_YAML)
        store = SaltConfigstore(str(tmp_path))

        settings = await store.get_settings(advanced=True)
        ids = _by_id(settings)

        # myapp.my_def: list -> multiline joined value; default mirrors value.
        my_def = ids["myapp.my_def"]
        assert my_def.value == "item1\nitem2\n"
        assert my_def.multiline is True
        assert my_def.default == "item1\nitem2\n"
        assert my_def.default_available is True
        assert my_def.node_id == ""

        # myapp.zdef: scalar default "vanilla" (Go shows chocolate only after a
        # local override, which is out of scope for the defaults tier).
        zdef = ids["myapp.zdef"]
        assert zdef.value == "vanilla"
        assert zdef.default == "vanilla"
        assert zdef.default_available is True
        assert zdef.node_id == ""

        # Only the two defaults-derived settings exist (no local/annotation tier).
        assert {s.id for s in settings} == {"myapp.my_def", "myapp.zdef"}

    async def test_only_defaults_yaml_files_are_walked(self, tmp_path: Path):
        # A sibling soc_*.yaml (annotation tier) and a non-defaults yaml must be
        # ignored by the defaults walk.
        _write_defaults(tmp_path, "salt/myapp/defaults.yaml", DEFAULTS_YAML)
        _write_defaults(tmp_path, "salt/myapp/soc_myapp.yaml", "myapp:\n  ignored: x\n")
        _write_defaults(tmp_path, "pillar/myapp/other.yaml", "myapp:\n  nope: y\n")
        store = SaltConfigstore(str(tmp_path))

        settings = await store.get_settings(advanced=True)
        ids = {s.id for s in settings}
        assert "myapp.ignored" not in ids
        assert "myapp.nope" not in ids

    async def test_walks_nested_defaults_yaml(self, tmp_path: Path):
        # defaults.yaml may live at any depth under default/.
        _write_defaults(tmp_path, "salt/a/defaults.yaml", "a:\n  one: 1\n")
        _write_defaults(tmp_path, "salt/b/c/defaults.yaml", "b:\n  two: 2\n")
        store = SaltConfigstore(str(tmp_path))

        settings = await store.get_settings(advanced=True)
        ids = _by_id(settings)
        assert ids["a.one"].value == "1"
        assert ids["b.two"].value == "2"

    async def test_descriptionless_defaults_are_advanced_and_filtered(self, tmp_path: Path):
        # Defaults have no descriptions, so post_process marks them advanced and
        # the non-advanced filter drops them entirely.
        _write_defaults(tmp_path, "salt/myapp/defaults.yaml", DEFAULTS_YAML)
        store = SaltConfigstore(str(tmp_path))

        advanced_settings = await store.get_settings(advanced=True)
        assert all(s.advanced for s in advanced_settings)

        basic_settings = await store.get_settings(advanced=False)
        assert basic_settings == []

    async def test_missing_default_dir_propagates_when_not_bypassing(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path / "does-not-exist"))
        with pytest.raises(OSError):
            await store.get_settings(advanced=True)

    async def test_missing_default_dir_tolerated_when_bypassing(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path / "does-not-exist"), bypass_errors=True)
        settings = await store.get_settings(advanced=True)
        assert settings == []

    async def test_bad_yaml_propagates_when_not_bypassing(self, tmp_path: Path):
        _write_defaults(tmp_path, "salt/myapp/defaults.yaml", "::: not valid yaml :::\n")
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(Exception):  # noqa: B017 - yaml/ValueError surfaced
            await store.get_settings(advanced=True)

    async def test_bad_yaml_tolerated_when_bypassing(self, tmp_path: Path):
        _write_defaults(tmp_path, "salt/myapp/defaults.yaml", "::: not valid yaml :::\n")
        _write_defaults(tmp_path, "salt/other/defaults.yaml", "other:\n  ok: 1\n")
        store = SaltConfigstore(str(tmp_path), bypass_errors=True)
        settings = await store.get_settings(advanced=True)
        # The good file is still parsed despite the bad one being skipped.
        assert _by_id(settings)["other.ok"].value == "1"


class TestUnimplementedWriteMethods:
    async def test_update_setting_not_implemented(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(NotImplementedError):
            await store.update_setting(Setting(id="x"), remove=False)

    async def test_sync_settings_not_implemented(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(NotImplementedError):
            await store.sync_settings()

    async def test_sync_module_not_implemented(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(NotImplementedError):
            await store.sync_module("mod", force=False)
