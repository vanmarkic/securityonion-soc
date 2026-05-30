"""Salt settings parsing helpers — ported from server/modules/salt/saltstore.go.

These are the pure building blocks behind ``SaltConfigstore.get_settings``:
turning a YAML pillar/defaults tree into a flat list of ``Setting`` objects
(``recursively_parse_settings``), then post-processing, filtering, and sorting
them. They are kept free of any I/O beyond ``parse_yaml`` so they can be unit
tested directly against Go's TestGetSettings expectations.
"""

from __future__ import annotations

import json
import logging
from functools import cmp_to_key
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from src.adapters.salt.jinja import unescape_jinja
from src.domain.config import Setting, new_setting

logger = logging.getLogger(__name__)


def render_scalar(value: Any) -> str:
    """Render a scalar the way Go's ``fmt.Sprintf("%v", value)`` would.

    YAML decodes scalars into Python ``str``/``int``/``float``/``bool``/``None``.
    Python's ``str()`` matches Go for str/int/float, but Go prints booleans as
    lowercase ``true``/``false`` and a nil value as ``<nil>``. We special-case
    those two so the emitted setting value is byte-identical to the Go store
    (e.g. the ``myapp.bool`` default renders as ``"true"``).
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "<nil>"
    return str(value)


def parse_yaml(path: str) -> dict[str, Any]:
    """Read and YAML-parse ``path`` into a dict (mirror saltstore.parseYaml)."""
    content = Path(path).read_text()
    mapped = yaml.safe_load(content)
    if mapped is None:
        return {}
    if not isinstance(mapped, dict):
        # Go unmarshals into map[string]interface{}; a non-mapping document is a
        # parse error there. Surface the same failure mode here.
        raise ValueError(f"YAML root of {path} is not a mapping")
    return mapped


def convert_to_json(item: Any) -> str:
    """Serialize a list/map item to JSON (mirror saltstore.convertToJson).

    Go's ``encoding/json`` sorts map keys and emits no whitespace between
    tokens, so we use ``sort_keys=True`` and compact separators to match the
    exact strings Go produces for list-of-list / list-of-map values.
    """
    try:
        return json.dumps(item, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError):
        logger.error("Failed to convert item to JSON; setting will be blank: %r", item)
        return ""


def _find_global(settings: list[Setting], setting_id: str) -> list[Setting]:
    return [s for s in settings if s.id == setting_id and s.node_id == ""]


def recursively_parse_settings(
    settings: list[Setting],
    mapped: dict[str, Any],
    prefix: str,
    minion: str,
    merge: bool,
) -> list[Setting]:
    """Flatten a nested YAML map into ``Setting`` objects.

    Ported from saltstore.recursivelyParseSettings. Dicts recurse (building a
    dotted id), lists become multiline values (each item joined with ``\\n``,
    list/map items JSON-encoded, empty strings skipped), and scalars render via
    ``render_scalar``. When ``minion`` is empty an emitted setting merges into an
    existing global (empty ``node_id``) setting of the same id; otherwise a new
    node-scoped setting is appended.
    """
    for setting_id, value in mapped.items():
        found_setting = True
        new_value = ""
        multiline = False

        new_prefix = prefix
        if new_prefix != "":
            new_prefix = new_prefix + "."

        if isinstance(value, dict):
            found_setting = False
            settings = recursively_parse_settings(
                settings, value, new_prefix + setting_id, minion, merge
            )
        elif isinstance(value, list):
            multiline = True
            for item in value:
                if isinstance(item, list | dict):
                    item_str = convert_to_json(item)
                else:
                    item_str = render_scalar(item)
                if item_str != "":
                    new_value = new_value + item_str + "\n"
        else:
            new_value = render_scalar(value)

        if found_setting:
            new_id = new_prefix + setting_id

            merged = False
            if minion == "":
                for existing in _find_global(settings, new_id):
                    existing.value = new_value
                    if existing.multiline != multiline:
                        logger.warning(
                            "Existing/Default setting's multiline attribute conflicts "
                            "with override multiline attribute (newId=%s, new=%s, old=%s)",
                            new_id,
                            multiline,
                            existing.multiline,
                        )
                        existing.multiline = multiline
                    merged = True

            if not merged:
                setting = new_setting(new_id)
                setting.value = new_value
                setting.node_id = minion
                setting.multiline = multiline
                settings.append(setting)

    return settings


def post_process(settings: list[Setting]) -> None:
    """Mark descriptionless settings advanced and unescape jinja (postProcess)."""
    for setting in settings:
        if len(setting.description) == 0:
            setting.advanced = True
        if setting.supports_jinja():
            setting.value = unescape_jinja(setting.value)


def filter_settings(settings: list[Setting], advanced: bool) -> list[Setting]:
    """Drop advanced settings unless ``advanced`` is requested (filter)."""
    if advanced:
        return settings
    return [s for s in settings if not s.advanced]


def _less(a: Setting, b: Setting) -> bool:
    # Faithful port of saltstore.sortSettings's comparator:
    #   (a.Id < b.Id && !hasSuffix(a.Id, "advanced")) || hasSuffix(b.Id, "advanced")
    return (a.id < b.id and not a.id.endswith("advanced")) or b.id.endswith("advanced")


def _cmp(a: Setting, b: Setting) -> int:
    if _less(a, b):
        return -1
    if _less(b, a):
        return 1
    return 0


def sort_settings(settings: list[Setting]) -> list[Setting]:
    """Sort settings using Go's sortSettings comparator (advanced ids trail)."""
    settings.sort(key=cmp_to_key(_cmp))
    return settings
