"""SaltConfigstore — configuration read/write backed by the saltstack tree.

Ported from server/modules/salt/saltstore.go (GetSettings and friends). This
unit implements ONLY the DEFAULTS tier of ``get_settings``: it walks
``<saltstack_dir>/default`` for files literally named ``defaults.yaml``, flattens
each into ``Setting`` objects, and records every parsed value as that setting's
default. Local pillar overrides and static annotations are a separate later unit
(see the TODO in ``get_settings``).

Authorization (Go's CheckAuthorized calls) is handled by the service/route layer
in this hexagonal codebase, not by the adapter.
"""

from __future__ import annotations

import logging
import os

from src.adapters.salt.settings import (
    filter_settings,
    parse_yaml,
    post_process,
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

        # TODO(next unit): parse local pillar overrides
        # (<saltstack_dir>/local/**/*.sls — soc_*, adv_*, and /minions/ files via
        # recursively_parse_settings(merge=True)/parse_advanced) and then the
        # static pillar annotations (<saltstack_dir>/default/**/soc_*.yaml via
        # recursively_parse_annotations). Those tiers mutate/extend `settings`
        # before post_process; they are intentionally out of scope here.

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

    async def update_setting(self, setting: Setting, remove: bool) -> None:
        # TODO(next unit): port saltstore.UpdateSetting.
        raise NotImplementedError

    async def sync_settings(self) -> None:
        # TODO(next unit): port saltstore.SyncSettings.
        raise NotImplementedError

    async def sync_module(self, module: str, force: bool) -> None:
        # TODO(next unit): port saltstore.SyncModule.
        raise NotImplementedError
