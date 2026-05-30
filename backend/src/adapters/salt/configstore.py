"""SaltConfigstore — configuration read/write backed by the saltstack tree.

Ported from server/modules/salt/saltstore.go (GetSettings and friends). This
unit implements the full READ path of ``get_settings``:

1. DEFAULTS tier: walk ``<saltstack_dir>/default`` for files literally named
   ``defaults.yaml``, flatten each into ``Setting`` objects, and record every
   parsed value as that setting's default.
2. LOCAL tier: walk ``<saltstack_dir>/local`` for ``*.sls`` files — ``soc_*``
   and ``/minions/`` files merge via ``recursively_parse_settings(merge=True)``;
   ``adv_*`` files become raw advanced settings via ``parse_advanced``.
3. ANNOTATION tier: walk ``<saltstack_dir>/default`` for ``soc_*.yaml`` files,
   attaching static metadata (title, description, etc.) via
   ``recursively_parse_annotations``.

Then post_process -> filter -> sort closes the pipeline.

Authorization (Go's CheckAuthorized calls) is handled by the service/route layer
in this hexagonal codebase, not by the adapter.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.adapters.salt.coercion import align_best_guess, align_type
from src.adapters.salt.jinja import escape_jinja
from src.adapters.salt.settings import (
    filter_settings,
    parse_advanced,
    parse_yaml,
    post_process,
    recursively_parse_annotations,
    recursively_parse_settings,
    rel_path_from_id,
    sort_settings,
)
from src.adapters.salt.validation import validate
from src.domain.config import Setting

logger = logging.getLogger(__name__)


class SaltConfigstore:
    """Read settings from (and, later, write them to) the saltstack tree."""

    def __init__(self, saltstack_dir: str, bypass_errors: bool = False) -> None:
        # Mirror Go Init: strip a single trailing slash from the configured dir.
        self.saltstack_dir = saltstack_dir.rstrip("/")
        self.bypass_errors = bypass_errors

    async def get_settings(self, advanced: bool) -> list[Setting]:
        settings: list[Setting] = []

        # Parse the default values first. The defaults walk only matches files
        # literally named "defaults.yaml" anywhere under <saltstack_dir>/default.
        default_dir = f"{self.saltstack_dir}/default"
        self._walk_defaults(default_dir, settings)

        # Since these are the defaults, record every setting's value as its
        # default so users can revert overrides (saltstore.go:166-171).
        for setting in settings:
            setting.default = setting.value
            setting.default_available = True

        # Now parse the local pillar overrides (<saltstack_dir>/local/**/*.sls).
        self._walk_local(f"{self.saltstack_dir}/local", settings)

        # Parse the static pillar annotations, to provide supporting details to
        # the settings parsed above (<saltstack_dir>/default/**/soc_*.yaml).
        self._walk_annotations(default_dir, settings)

        post_process(settings)
        return sort_settings(filter_settings(settings, advanced))

    def _walk_defaults(self, default_dir: str, settings: list[Setting]) -> None:
        """Walk ``default_dir`` and merge every ``defaults.yaml`` into settings.

        Mirrors the filepath.Walk over <saltstack_dir>/default in GetSettings,
        including its bypass_errors semantics: when bypassing, read/parse errors
        (and a missing root directory) are logged and skipped; otherwise they
        propagate to the caller.
        """
        if not os.path.isdir(default_dir):
            # filepath.Walk surfaces an lstat error for a missing root; replicate
            # that propagation here (and tolerate it when bypassing errors).
            if self.bypass_errors:
                logger.warning("Bypassing error while parsing defaults: missing %s", default_dir)
                return
            raise FileNotFoundError(f"{default_dir}: no such file or directory")

        for root, _dirs, files in os.walk(default_dir):
            for name in files:
                if name != "defaults.yaml":
                    continue
                path = os.path.join(root, name)
                try:
                    mapped = parse_yaml(path)
                except Exception:
                    if self.bypass_errors:
                        logger.warning("Bypassing error while parsing defaults: %s", path)
                        continue
                    raise
                recursively_parse_settings(settings, mapped, "", "", False)

    def _walk_local(self, local_dir: str, settings: list[Setting]) -> None:
        """Walk ``local_dir`` and merge every ``*.sls`` override into settings.

        Mirrors the filepath.Walk over <saltstack_dir>/local in GetSettings:
        each ``*.sls`` file's basename (minus ``.sls``) is the setting id, a
        ``/minions/`` path component scopes it to a node, ``adv_*`` files become
        raw advanced settings, and ``soc_*``/minion files merge through
        ``recursively_parse_settings(merge=True)``. bypass_errors semantics match
        the defaults walk: errors are logged and skipped when bypassing, else
        propagate.
        """
        if not os.path.isdir(local_dir):
            if self.bypass_errors:
                logger.warning("Bypassing error while parsing local pillars: missing %s", local_dir)
                return
            raise FileNotFoundError(f"{local_dir}: no such file or directory")

        for root, dirs, files in os.walk(local_dir):
            # Visit lexically, like Go's filepath.Walk (order affects merges).
            dirs.sort()
            for name in sorted(files):
                if not name.endswith(".sls"):
                    continue
                path = os.path.join(root, name)
                setting_id = name[: -len(".sls")]
                minion_id = ""
                is_minion = "/minions/" in path

                try:
                    if setting_id.startswith("adv_"):
                        setting_id = setting_id[len("adv_") :]
                        if is_minion:
                            minion_id = setting_id
                            setting_id = "advanced"
                        else:
                            setting_id = setting_id + ".advanced"
                        parse_advanced(path, settings, minion_id, setting_id)
                    elif setting_id.startswith("soc_") or is_minion:
                        if is_minion:
                            minion_id = setting_id
                        mapped = parse_yaml(path)
                        recursively_parse_settings(settings, mapped, "", minion_id, True)
                except Exception:
                    if self.bypass_errors:
                        logger.warning("Bypassing error while parsing local pillars: %s", path)
                        continue
                    raise

    def _walk_annotations(self, default_dir: str, settings: list[Setting]) -> None:
        """Walk ``default_dir`` and apply every ``soc_*.yaml`` annotation.

        Mirrors the second filepath.Walk over <saltstack_dir>/default in
        GetSettings, matching files whose basename has the ``soc_`` prefix and
        ``.yaml`` suffix and attaching their metadata via
        ``recursively_parse_annotations``. Runs AFTER defaults + local so
        annotations land on existing settings (and may add annotation-only ones).
        """
        if not os.path.isdir(default_dir):
            if self.bypass_errors:
                logger.warning(
                    "Bypassing error while parsing annotations: missing %s", default_dir
                )
                return
            raise FileNotFoundError(f"{default_dir}: no such file or directory")

        for root, dirs, files in os.walk(default_dir):
            dirs.sort()
            for name in sorted(files):
                if not (name.startswith("soc_") and name.endswith(".yaml")):
                    continue
                path = os.path.join(root, name)
                try:
                    mapped = parse_yaml(path)
                except Exception:
                    if self.bypass_errors:
                        logger.warning("Bypassing error while parsing annotations: %s", path)
                        continue
                    raise
                recursively_parse_annotations(
                    settings, mapped, "", saltstack_dir=self.saltstack_dir
                )

    @staticmethod
    def _get_setting(settings: list[Setting], setting_id: str) -> Setting | None:
        """Find a setting definition by id (mirror saltstore.GetSetting)."""
        for setting in settings:
            if setting.id == setting_id:
                return setting
        return None

    async def update_setting(self, setting: Setting, remove: bool) -> None:
        """Write (or remove) a setting in the saltstack tree (port UpdateSetting).

        Faithful port of saltstore.UpdateSetting orchestration:

        1. Split the id into dotted sections (an empty id is rejected).
        2. Pull the full (advanced) settings list and locate this id's definition;
           a readonly def is refused, otherwise its metadata is copied onto the
           incoming setting (so routing/validation use the authoritative schema).
        3. For a write (not remove): jinja-escape jinja-supporting values, then
           validate non-array, non-file values against their syntax.
        4. Route to one of three on-disk shapes — ADVANCED (raw .sls), FILE (raw
           file under local/salt), or NORMAL (recursive YAML set/delete in a
           soc_/minion pillar .sls) — and persist.

        Go's CheckAuthorized("write", "config") is intentionally NOT ported; the
        service/route layer enforces authorization in this codebase.
        """
        sections = setting.id.split(".")
        if setting.id == "":  # split("") -> [""], but an empty id is invalid.
            raise ValueError(f"Invalid setting id: {setting.id}")

        # Always pull advanced settings on update since the incoming setting may
        # not be properly flagged as advanced.
        settings = await self.get_settings(advanced=True)
        setting_def = self._get_setting(settings, setting.id)
        if setting_def is None:
            logger.info(
                "Setting definition not found; assuming new, undefined setting (id=%s)",
                setting.id,
            )
        else:
            if setting_def.readonly:
                raise ValueError("Unable to modify or remove a readonly setting")
            setting.syntax = setting_def.syntax
            setting.description = setting_def.description
            setting.title = setting_def.title
            setting.multiline = setting_def.multiline
            setting.advanced = setting_def.advanced
            setting.forced_type = setting_def.forced_type
            setting.default = setting_def.default
            setting.default_available = setting_def.default_available
            setting.file = setting_def.file
            setting.jinja_escaped = setting_def.jinja_escaped
            setting.ui_elements = setting_def.ui_elements

        if not remove:
            if setting.supports_jinja():
                setting.value = escape_jinja(setting.value)

            if not setting.forced_type.startswith("[]") and not setting.file:
                # Array-valued settings carry \n separators and are validated
                # during type alignment; files may disable Jinja rendering in
                # their salt state, so both are skipped here.
                validate(setting.value, setting.syntax)

        if len(sections) <= 2 and sections[-1] == "advanced":
            self._write_advanced(setting, sections)
        elif setting.file:
            self._write_file(setting, remove)
        else:
            self._write_normal(setting, sections, remove)

    def _write_advanced(self, setting: Setting, sections: list[str]) -> None:
        """Write a raw advanced-settings .sls file (ADVANCED routing branch).

        Matches Go: the whole value is written verbatim regardless of ``remove``.
        """
        if setting.node_id == "":
            path = f"{self.saltstack_dir}/local/pillar/{sections[0]}/adv_{sections[0]}.sls"
        else:
            path = f"{self.saltstack_dir}/local/pillar/minions/adv_{setting.node_id}.sls"
        self._write_bytes(path, setting.value)

    def _write_file(self, setting: Setting, remove: bool) -> None:
        """Write/remove a custom file under local/salt (FILE routing branch)."""
        path = f"{self.saltstack_dir}/local/salt/{rel_path_from_id(setting.id)}"
        if not remove:
            self._write_bytes(path, setting.value)
        else:
            os.remove(path)

    def _write_normal(self, setting: Setting, sections: list[str], remove: bool) -> None:
        """Recursively set/delete a setting in a pillar .sls (NORMAL branch)."""
        if setting.node_id == "":
            path = f"{self.saltstack_dir}/local/pillar/{sections[0]}/soc_{sections[0]}.sls"
        else:
            path = f"{self.saltstack_dir}/local/pillar/minions/{setting.node_id}.sls"

        # parse_yaml propagates a read error for a missing file, matching Go's
        # parseYaml returning (nil, err) and UpdateSetting's `if err == nil` guard
        # that then skips the write and surfaces the error.
        mapped = parse_yaml(path)
        if not remove:
            update_setting_yaml(mapped, sections, setting)
        else:
            delete_setting_yaml(mapped, sections)
        write_yaml(path, mapped)

    @staticmethod
    def _write_bytes(path: str, value: str) -> None:
        """Write ``value`` as bytes (mode 0600), creating parent dirs."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value.encode())
        os.chmod(path, 0o600)

    async def sync_settings(self) -> None:
        # TODO(next unit): port saltstore.SyncSettings.
        raise NotImplementedError

    async def sync_module(self, module: str, force: bool) -> None:
        # TODO(next unit): port saltstore.SyncModule.
        raise NotImplementedError


def update_setting_yaml(
    mapped: dict[str, Any], sections: list[str], setting: Setting
) -> None:
    """Recursively set a setting's value in a nested map (port updateSetting).

    Descends ``mapped`` along ``sections``, creating intermediate maps for a new
    override hierarchy. At the leaf the value is type-coerced: a ``forced_type``
    drives list/forced coercion (deferred to the next unit), otherwise the new
    value is aligned to the existing value's type (or, for an absent value with a
    default, to the default's best-guess type).
    """
    if mapped is None or len(sections) == 0:
        raise ValueError("Settings map to section id mismatch")

    name = sections[0]
    child = mapped.get(name)
    if child is None and len(sections) > 1:
        # New override: the parent hierarchy doesn't exist yet. Create it.
        child = {}
        mapped[name] = child

    if isinstance(child, dict):
        if len(sections) == 1:
            raise ValueError("Unexpected setting value of map type during update")
        update_setting_yaml(child, sections[1:], setting)
        return

    if len(sections) == 1:
        value = setting.value
        if setting.forced_type != "":
            # B2: forced_type coercion (force_type + coerce_map_list_field_types).
            raise NotImplementedError("# B2: forced_type")
        current_value = mapped.get(name)
        if current_value is None and setting.default_available:
            current_value = align_best_guess(setting.default)
        mapped[name] = align_type(current_value, value.strip())


def delete_setting_yaml(mapped: dict[str, Any], sections: list[str]) -> bool:
    """Recursively delete a setting and prune empty parents (port deleteSetting).

    Returns whether ``mapped`` became empty as a result (so a caller can prune it).
    """
    if mapped is None or len(sections) == 0:
        raise ValueError("Settings map to section id mismatch")

    name = sections[0]
    child = mapped.get(name)
    if child is not None:
        if isinstance(child, dict):
            if len(sections) == 1:
                raise ValueError("Unexpected setting value of map type during delete")
            empty = delete_setting_yaml(child, sections[1:])
            if empty:
                del mapped[name]
        else:
            del mapped[name]

    return len(mapped) == 0


def write_yaml(path: str, mapped: dict[str, Any]) -> None:
    """Serialize ``mapped`` to YAML at ``path`` (mode 0600); mirror writeYaml."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    contents = yaml.safe_dump(mapped, default_flow_style=False, sort_keys=True)
    target.write_text(contents)
    os.chmod(path, 0o600)
