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

from src.adapters.salt.settings import (
    filter_settings,
    parse_advanced,
    parse_yaml,
    post_process,
    recursively_parse_annotations,
    recursively_parse_settings,
    sort_settings,
)
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

    async def update_setting(self, setting: Setting, remove: bool) -> None:
        # TODO(next unit): port saltstore.UpdateSetting.
        raise NotImplementedError

    async def sync_settings(self) -> None:
        # TODO(next unit): port saltstore.SyncSettings.
        raise NotImplementedError

    async def sync_module(self, module: str, force: bool) -> None:
        # TODO(next unit): port saltstore.SyncModule.
        raise NotImplementedError
