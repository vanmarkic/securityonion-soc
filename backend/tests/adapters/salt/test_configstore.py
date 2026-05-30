"""Tests for SaltConfigstore.get_settings — full read path.

Anchored to server/modules/salt/saltstore_test.go TestGetSettings. The Go test
mixes defaults, local-pillar overrides, and static annotations; this unit now
implements all three walks, so we reproduce the exact fixture tree under
test_resources/saltstack and assert the SAME settings Go's TestGetSettings
asserts (defaults + local overrides + annotations + advanced + minion).
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


def _write_local(saltstack_dir: Path, relative: str, content: str) -> None:
    target = saltstack_dir / "local" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _ensure_local(saltstack_dir: Path) -> None:
    """Mirror the Go fixture tree, which always has a (possibly empty) local/.

    Go's GetSettings walks <saltstack_dir>/local; a missing root propagates an
    lstat error when not bypassing, so the real saltstack tree always has it.
    """
    (saltstack_dir / "local").mkdir(parents=True, exist_ok=True)


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
        _ensure_local(tmp_path)
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
        # The defaults walk only matches files literally named defaults.yaml; a
        # plain (non soc_) yaml is ignored entirely, and a soc_*.yaml is parsed
        # only as annotations (never as a defaults value source).
        _write_defaults(tmp_path, "salt/myapp/defaults.yaml", DEFAULTS_YAML)
        _write_defaults(tmp_path, "pillar/myapp/other.yaml", "myapp:\n  nope: y\n")
        _ensure_local(tmp_path)
        store = SaltConfigstore(str(tmp_path))

        settings = await store.get_settings(advanced=True)
        ids = {s.id for s in settings}
        # Neither a defaults value nor an annotation was produced for these.
        assert "myapp.nope" not in ids

    async def test_walks_nested_defaults_yaml(self, tmp_path: Path):
        # defaults.yaml may live at any depth under default/.
        _write_defaults(tmp_path, "salt/a/defaults.yaml", "a:\n  one: 1\n")
        _write_defaults(tmp_path, "salt/b/c/defaults.yaml", "b:\n  two: 2\n")
        _ensure_local(tmp_path)
        store = SaltConfigstore(str(tmp_path))

        settings = await store.get_settings(advanced=True)
        ids = _by_id(settings)
        assert ids["a.one"].value == "1"
        assert ids["b.two"].value == "2"

    async def test_descriptionless_defaults_are_advanced_and_filtered(self, tmp_path: Path):
        # Defaults have no descriptions, so post_process marks them advanced and
        # the non-advanced filter drops them entirely.
        _write_defaults(tmp_path, "salt/myapp/defaults.yaml", DEFAULTS_YAML)
        _ensure_local(tmp_path)
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


# Byte-for-byte ports of the Go fixture tree under
# server/modules/salt/test_resources/saltstack. These drive the full read-path
# integration test below, anchored to Go's TestGetSettings.
FIXTURE_DEFAULT_SALT_DEFAULTS = (
    "myapp:\n"
    "  my_def:\n"
    "  - item1\n"
    "  - item2\n"
    "  zdef: vanilla"
)
FIXTURE_DEFAULT_SALT_SOC = """myapp:
  my_def:
    jinjaEscaped: True
  foo__txt:
    description: Test file annotation
    file: True
  ro:
    description: read only setting
    readonly: True
  ui_map_typed:
    description: Map list with typed UI elements
    forcedType: "[]{}"
    uiElements:
    - field: port
      label: Port
      forcedType: int
    - field: enabled
      label: Enabled
      forcedType: bool
    - field: name
      label: Name
  ui_json:
    description: UI elements for JSON packing
    uiElements:
    - field: something
      label: something nice
      forcedType: bool
      multiline: false
      default: true
      required: false
      readonly: true
    - field: another
      label: another thing
      forcedType: "[]string"
      options:
      - blue
      - red
      - green
      default: red
    - field: one more
      label: But wait there's more
      multiline: True
      required: true
      regex: "^abc$"
      regexFailureMessage: must conform
"""
FIXTURE_DEFAULT_PILLAR_SOC = """myapp:
  int:
    description: test desc
    global: true
    readonly: false
    regex: "([0-9]+){3}"
    regexFailureMessage: Invalid!
  int_nodefault:
    description: no default provided
    global: true
    forcedType: "int"
  int_list_nodefault:
    description: no default provided
    global: true
    forcedType: "[]int"
"""
FIXTURE_LOCAL_SOC = """myapp:
  empty_lists:
    list_str: []
    list_bool: []
    list_float: []
    list_int: []
    list_list_str: []
    list_map_str: []
  lists:
    list_str:
      - foo
      - bar
    list_bool:
      - true
      - False
    list_float:
      - 1.24
      - 2.2
    list_int:
      - 3
      - 24
    list_list_str:\x20
      -
        - item1
        - item2
      -
        - item3
        - item4
    list_map_str:\x20
      - key1: value1
        key2: value2
      - key1: value3
        key2: value4
  int: 123
  float: 3.5
  str: my_str
  bool: true
  zdef: chocolate
  ui_json: "{\\"something\\":\\"here\\",\\"another\\":\\"else\\"},{\\"something\\":\\"here2\\",\\"another\\":\\"else2\\"}"
"""
FIXTURE_LOCAL_ADV = "myapp:\n  global: advanced\n"
FIXTURE_LOCAL_MINION = "myapp:\n  foo: minion-born\n  bar: minion-override\n  zdef: strawberry\n"


def _build_full_fixture(saltstack_dir: Path) -> None:
    """Recreate the Go TestGetSettings saltstack tree under ``saltstack_dir``."""
    _write_defaults(saltstack_dir, "salt/myapp/defaults.yaml", FIXTURE_DEFAULT_SALT_DEFAULTS)
    _write_defaults(saltstack_dir, "salt/myapp/soc_myapp.yaml", FIXTURE_DEFAULT_SALT_SOC)
    _write_defaults(saltstack_dir, "pillar/myapp/soc_myapp.yaml", FIXTURE_DEFAULT_PILLAR_SOC)
    _write_defaults(saltstack_dir, "salt/myapp/foo.txt", "anything")
    _write_defaults(saltstack_dir, "salt/myapp/some_file.txt", "old")

    _write_local(saltstack_dir, "pillar/myapp/soc_myapp.sls", FIXTURE_LOCAL_SOC)
    _write_local(saltstack_dir, "pillar/myapp/adv_myapp.sls", FIXTURE_LOCAL_ADV)
    _write_local(saltstack_dir, "pillar/minions/normal_import.sls", FIXTURE_LOCAL_MINION)
    _write_local(saltstack_dir, "pillar/minions/empty_standalone.sls", "")
    _write_local(saltstack_dir, "salt/myapp/foo.txt", "old")
    _write_local(saltstack_dir, "salt/myapp/some_file.txt", "old")


# The COMPLETE ordered (id, node_id, value) triples Go's TestGetSettings asserts,
# after re-sorting by (Id, NodeId) like the Go test does.
EXPECTED_GO_SETTINGS = [
    ("myapp.advanced", "", "myapp:\n  global: advanced\n"),
    ("myapp.bar", "normal_import", "minion-override"),
    ("myapp.bool", "", "true"),
    ("myapp.empty_lists.list_bool", "", ""),
    ("myapp.empty_lists.list_float", "", ""),
    ("myapp.empty_lists.list_int", "", ""),
    ("myapp.empty_lists.list_list_str", "", ""),
    ("myapp.empty_lists.list_map_str", "", ""),
    ("myapp.empty_lists.list_str", "", ""),
    ("myapp.float", "", "3.5"),
    ("myapp.foo", "normal_import", "minion-born"),
    ("myapp.foo__txt", "", "old"),
    ("myapp.int", "", "123"),
    ("myapp.int_list_nodefault", "", ""),
    ("myapp.int_nodefault", "", ""),
    ("myapp.lists.list_bool", "", "true\nfalse\n"),
    ("myapp.lists.list_float", "", "1.24\n2.2\n"),
    ("myapp.lists.list_int", "", "3\n24\n"),
    ("myapp.lists.list_list_str", "", '["item1","item2"]\n["item3","item4"]\n'),
    (
        "myapp.lists.list_map_str",
        "",
        '{"key1":"value1","key2":"value2"}\n{"key1":"value3","key2":"value4"}\n',
    ),
    ("myapp.lists.list_str", "", "foo\nbar\n"),
    ("myapp.my_def", "", "item1\nitem2\n"),
    ("myapp.ro", "", ""),  # annotation-only (no defaults / local value)
    ("myapp.str", "", "my_str"),
    (
        "myapp.ui_json",
        "",
        '{"something":"here","another":"else"},{"something":"here2","another":"else2"}',
    ),
    ("myapp.ui_map_typed", "", ""),
    ("myapp.zdef", "", "chocolate"),
    ("myapp.zdef", "normal_import", "strawberry"),
]


def _sorted_like_go(settings: list[Setting]) -> list[Setting]:
    return sorted(settings, key=lambda s: (s.id, s.node_id))


class TestGetSettingsFullReadPath:
    """Port of Go saltstore_test.go TestGetSettings — defaults+local+annotations."""

    async def test_matches_go_test_get_settings(self, tmp_path: Path):
        _build_full_fixture(tmp_path)
        store = SaltConfigstore(str(tmp_path))

        settings = _sorted_like_go(await store.get_settings(advanced=True))
        by = {(s.id, s.node_id): s for s in settings}

        # Same count of settings as Go (TEST_SETTINGS_COUNT == 28).
        assert len(settings) == 28

        # myapp.advanced — the adv_myapp.sls global advanced override.
        adv = by[("myapp.advanced", "")]
        assert adv.value == "myapp:\n  global: advanced\n"
        assert adv.syntax == "yaml"
        assert adv.global_ is True
        assert adv.node is False
        assert adv.multiline is True

        # Minion (node) overrides from normal_import.sls.
        assert by[("myapp.bar", "normal_import")].value == "minion-override"
        assert by[("myapp.foo", "normal_import")].value == "minion-born"

        # Scalars / lists from the local soc_myapp.sls override.
        assert by[("myapp.bool", "")].value == "true"
        assert by[("myapp.float", "")].value == "3.5"
        assert by[("myapp.str", "")].value == "my_str"
        assert by[("myapp.lists.list_bool", "")].value == "true\nfalse\n"
        assert by[("myapp.lists.list_float", "")].value == "1.24\n2.2\n"
        assert by[("myapp.lists.list_int", "")].value == "3\n24\n"
        assert (
            by[("myapp.lists.list_list_str", "")].value
            == '["item1","item2"]\n["item3","item4"]\n'
        )
        assert (
            by[("myapp.lists.list_map_str", "")].value
            == '{"key1":"value1","key2":"value2"}\n{"key1":"value3","key2":"value4"}\n'
        )
        assert by[("myapp.lists.list_str", "")].value == "foo\nbar\n"

        # Empty lists stay empty.
        for sub in ("list_bool", "list_float", "list_int", "list_list_str", "list_map_str", "list_str"):
            assert by[(f"myapp.empty_lists.{sub}", "")].value == ""

        # myapp.my_def — defaults list value (annotation only sets jinjaEscaped).
        assert by[("myapp.my_def", "")].value == "item1\nitem2\n"

        # File annotation: value is read from local/salt/myapp/foo.txt ("old"),
        # default from default/salt/myapp/foo.txt ("anything").
        foo_txt = by[("myapp.foo__txt", "")]
        assert foo_txt.file is True
        assert foo_txt.value == "old"
        assert foo_txt.default == "anything"
        assert foo_txt.multiline is True

        # myapp.int — annotated from default/pillar/myapp/soc_myapp.yaml.
        myint = by[("myapp.int", "")]
        assert myint.value == "123"
        assert myint.regex == "([0-9]+){3}"
        assert myint.regex_failure_message == "Invalid!"
        assert myint.description == "test desc"
        assert myint.global_ is True
        assert myint.readonly is False

        # Annotation-only settings (no default/local value), with forcedType.
        ilnd = by[("myapp.int_list_nodefault", "")]
        assert ilnd.value == ""
        assert ilnd.description == "no default provided"
        assert ilnd.global_ is True
        assert ilnd.forced_type == "[]int"

        ind = by[("myapp.int_nodefault", "")]
        assert ind.value == ""
        assert ind.description == "no default provided"
        assert ind.global_ is True
        assert ind.forced_type == "int"

        # myapp.ro — readonly annotation.
        assert by[("myapp.ro", "")].readonly is True

        # myapp.ui_json — JSON value carried, three UI elements attached.
        ui_json = by[("myapp.ui_json", "")]
        assert ui_json.value == (
            '{"something":"here","another":"else"},'
            '{"something":"here2","another":"else2"}'
        )
        assert len(ui_json.ui_elements) == 3

        # myapp.ui_map_typed — forcedType + three UI elements, no value.
        ui_map = by[("myapp.ui_map_typed", "")]
        assert ui_map.value == ""
        assert ui_map.forced_type == "[]{}"
        assert len(ui_map.ui_elements) == 3

        # myapp.zdef — global value overridden vanilla -> chocolate; node override.
        zdef = by[("myapp.zdef", "")]
        assert zdef.value == "chocolate"
        assert zdef.default == "vanilla"
        zdef_node = by[("myapp.zdef", "normal_import")]
        assert zdef_node.value == "strawberry"

        # Full id/node_id set matches Go exactly.
        assert sorted((s.id, s.node_id) for s in settings) == sorted(
            (eid, enid) for (eid, enid, _v) in EXPECTED_GO_SETTINGS
        )

    async def test_advanced_false_filters_advanced_out(self, tmp_path: Path):
        _build_full_fixture(tmp_path)
        store = SaltConfigstore(str(tmp_path))

        basic = await store.get_settings(advanced=False)
        # Every descriptionless / advanced-marked setting is dropped.
        assert all(not s.advanced for s in basic)
        ids = {s.id for s in basic}
        # The raw advanced override and descriptionless defaults are gone.
        assert "myapp.advanced" not in ids
        assert "myapp.bool" not in ids
        # Described annotated settings survive.
        assert "myapp.int" in ids
        assert "myapp.ro" in ids


class TestWriteMethodGuards:
    async def test_update_setting_rejects_empty_id(self, tmp_path: Path):
        # update_setting is implemented now (see test_configstore_write.py); an
        # empty id is still rejected before any I/O.
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(ValueError, match="Invalid setting id"):
            await store.update_setting(Setting(id=""), remove=False)

    async def test_sync_settings_requires_relay(self, tmp_path: Path):
        # sync_settings is implemented now (see test_configstore_write.py); with
        # no relay wired it raises a clear error rather than NotImplementedError.
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(RuntimeError, match="no relay configured"):
            await store.sync_settings()

    async def test_sync_module_requires_relay(self, tmp_path: Path):
        store = SaltConfigstore(str(tmp_path))
        with pytest.raises(RuntimeError, match="no relay configured"):
            await store.sync_module("mod", force=False)
