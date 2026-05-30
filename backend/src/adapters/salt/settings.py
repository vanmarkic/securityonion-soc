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
from src.domain.config import Setting, UiElement, new_setting

logger = logging.getLogger(__name__)


def render_scalar(value: Any) -> str:
    """Render a scalar the way Go's ``fmt.Sprintf("%v", value)`` would.

    YAML decodes scalars into Python ``str``/``int``/``float``/``bool``/``None``.
    Python's ``str()`` matches Go for str/int/float, but Go prints booleans as
    lowercase ``true``/``false`` and a nil value as ``<nil>``. We special-case
    those two so the emitted setting value is byte-identical to the Go store
    (e.g. the ``myapp.bool`` default renders as ``"true"``).

    Caveat: whole-number floats (Go ``3`` vs Python ``3.0``) and ``inf``/``nan``
    do not render byte-identically to Go's ``%v``; these fall outside the
    realistic Salt-defaults fixture space and are not special-cased here.
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


def cast_to_string_array(value: Any) -> list[str]:
    """Coerce a YAML list into a list of strings (mirror castToStringArray).

    Go asserts ``value.([]interface{})`` then ``tmp.(string)`` on each item, so a
    non-list value or a non-string item raises (matching Go's panic semantics).
    """
    if not isinstance(value, list):
        raise TypeError(f"expected a list, got {type(value).__name__}")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"expected a string list item, got {type(item).__name__}")
        out.append(item)
    return out


def read_file(path: str) -> str:
    """Read a file's contents as text (mirror saltstore.readFile)."""
    return Path(path).read_text()


def rel_path_from_id(setting_id: str) -> str:
    """Map a setting id to a salt file relative path (mirror relPathFromId).

    Only a DOUBLE underscore (``__``) becomes a dot; a single underscore is left
    alone. Example: ``soc.files.soc.banner__md`` -> ``soc/files/soc/banner.md``
    (and ``myapp.foo__txt`` -> ``myapp/foo.txt``).
    """
    relpath = setting_id.replace(".", "/")
    relpath = relpath.replace("__", ".")
    relpath = relpath.replace("..", "____")  # Shenannigans (faithful to Go)
    return relpath


def _parse_ui_element(tmp_map: dict[str, Any]) -> UiElement:
    """Build a UiElement from one annotation map (mirror the inner switch)."""
    element = UiElement()
    for key, value in tmp_map.items():
        if key == "field":
            element.field = value
        elif key == "label":
            element.label = value
        elif key == "forcedType":
            element.forced_type = value
        elif key == "multiline":
            element.multiline = value
        elif key == "options":
            element.options = cast_to_string_array(value)
        elif key == "default":
            element.default = value
        elif key == "required":
            element.required = value
        elif key == "readonly":
            element.readonly = value
        elif key == "regex":
            element.regex = render_scalar(value)
        elif key == "regexFailureMessage":
            element.regex_failure_message = value
    return element


def update_setting_with_annotation(
    setting: Setting,
    annotations: dict[str, Any],
    *,
    saltstack_dir: str = "",
) -> None:
    """Apply an annotation block to a Setting (port updateSettingWithAnnotation).

    A switch over annotation keys mapping each onto its corresponding ``Setting``
    field. String-valued keys go through ``render_scalar`` (Go's ``%v``); boolean
    and string-typed keys are taken as-is (Go's ``value.(bool)`` / ``.(string)``).
    The ``file`` annotation additionally reads default/value contents from the
    saltstack tree (needs ``saltstack_dir``).
    """
    for key, value in annotations.items():
        if key == "title":
            setting.title = render_scalar(value)
        elif key == "description":
            setting.description = render_scalar(value)
        elif key == "readonly":
            setting.readonly = value
        elif key == "readonlyUi":
            setting.readonly_ui = value
        elif key == "global":
            setting.global_ = value
        elif key == "multiline":
            setting.multiline = value
        elif key == "node":
            setting.node = value
        elif key == "sensitive":
            setting.sensitive = value
        elif key == "regex":
            setting.regex = render_scalar(value)
        elif key == "regexFailureMessage":
            setting.regex_failure_message = render_scalar(value)
        elif key == "advanced":
            setting.advanced = value
        elif key == "helpLink":
            setting.help_link = render_scalar(value)
        elif key == "syntax":
            setting.syntax = render_scalar(value)
        elif key == "forcedType":
            setting.forced_type = render_scalar(value)
        elif key == "file":
            # Special annotation: the contents of a salt file become the value.
            setting.file = value
            if setting.file:
                setting.multiline = True
                relpath = rel_path_from_id(setting.id)
                try:
                    setting.default = read_file(f"{saltstack_dir}/default/salt/{relpath}")
                    setting.default_available = True
                except OSError:
                    pass
                try:
                    setting.value = read_file(f"{saltstack_dir}/local/salt/{relpath}")
                except OSError:
                    setting.value = ""
                if setting.value == "":
                    setting.value = setting.default
        elif key == "duplicates":
            setting.duplicates = value
        elif key == "jinjaEscaped":
            setting.jinja_escaped = value
        elif key == "options":
            setting.options = cast_to_string_array(value)
        elif key == "optionSeparator":
            setting.option_separator = value
        elif key == "required":
            setting.required = value
        elif key == "uiElements":
            for tmp in value:
                if isinstance(tmp, dict):
                    setting.ui_elements.append(_parse_ui_element(tmp))
                else:
                    logger.error("Invalid annotation; cannot cast to map")
        elif key == "uiElementsDeleteMessage":
            setting.ui_elements_delete_message = value


def recursively_parse_annotations(
    settings: list[Setting],
    mapped: dict[str, Any],
    prefix: str,
    *,
    saltstack_dir: str = "",
) -> tuple[list[Setting], bool]:
    """Attach static annotation metadata onto settings (recursivelyParseAnnotations).

    Walks the nested annotation map, building a dotted id as it descends. A node
    is an "end of branch" (an annotation block, not just a grouping container)
    when recursing into it reports ``found_annotation`` — i.e. that child level
    contained a non-dict value (an actual annotation key like ``title``). At an
    end-of-branch the matching existing setting(s) (by id) are updated via
    ``update_setting_with_annotation``, applying the sensitive masking rule; if
    no setting exists, an annotation-only setting is created.

    Returns ``(settings, found_annotation)`` where ``found_annotation`` is True
    iff THIS level held a non-dict child (signalling the parent it is at an
    end-of-branch).
    """
    found_annotation = False
    for setting_id, value in mapped.items():
        new_prefix = prefix
        if new_prefix != "":
            new_prefix = new_prefix + "."
        new_id = new_prefix + setting_id

        if isinstance(value, dict):
            settings, end_of_branch = recursively_parse_annotations(
                settings, value, new_id, saltstack_dir=saltstack_dir
            )
            if end_of_branch:
                found_existing = False
                for setting in settings:
                    if setting.id == new_id:
                        update_setting_with_annotation(
                            setting, value, saltstack_dir=saltstack_dir
                        )
                        # Do not allow sensitive settings to be transmitted to
                        # remote API clients.
                        if setting.sensitive:
                            setting.value = "******"
                            setting.default = ""
                        found_existing = True
                if not found_existing:
                    # Add a new setting since none exists for this annotation.
                    setting = new_setting(new_id)
                    update_setting_with_annotation(
                        setting, value, saltstack_dir=saltstack_dir
                    )
                    settings.append(setting)
                    logger.debug("Found annotation without a setting (id=%s)", new_id)
        else:
            found_annotation = True
    return settings, found_annotation


def parse_advanced(
    path: str,
    settings: list[Setting],
    minion: str,
    setting_id: str,
) -> list[Setting]:
    """Read an advanced (raw YAML) override file into a Setting (parseAdvanced).

    The whole file content becomes a single multiline ``yaml``-syntax setting. A
    minion-scoped file yields a node setting; otherwise a global one. A read
    error is swallowed (matching Go's ``if err == nil`` guard).
    """
    try:
        content = read_file(path)
    except OSError:
        return settings

    setting = new_setting(setting_id)
    if minion != "":
        setting.global_ = False
        setting.node = True
    else:
        setting.global_ = True
        setting.node = False
    setting.value = content
    setting.node_id = minion
    setting.multiline = True
    setting.syntax = "yaml"
    settings.append(setting)
    return settings
