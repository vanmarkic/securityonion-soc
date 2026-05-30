"""Setting value type coercion — ported from server/modules/salt/saltstore.go.

When a setting is written back into a pillar YAML map its string value must be
coerced to the right Python type so the re-serialized YAML keeps the original
shape (an int stays an int, a bool stays a bool, etc.). Two entry points mirror
the Go store:

* :func:`align_best_guess` — used for brand-new values (no existing type to
  match): guess int, then float, then bool, then ``\\n``-separated list, then a
  JSON object/array, else keep the string.
* :func:`align_type` — used when an existing value is present: coerce the new
  string to the SAME type as the old value (parse failures surface as errors).

The LIST coercers (``[]int`` / ``[]bool`` / ``[]float`` / ``[][]`` / ``[]{}``)
mirror Go's alignInt64List / alignBoolList / alignFloat64List / alignListList /
alignMapList: split the incoming value on ``\\n`` and parse each line (scalars via
the ``parse_*`` helpers; list/map lines via ``json.loads``), raising on any bad
line and yielding an empty list for empty input. :func:`force_type` and
:func:`coerce_map_list_field_types` drive a setting's declared ``forcedType``.

Go uses ``strconv`` for parsing, whose acceptance and error strings differ from
Python's builtins; :func:`parse_int`, :func:`parse_float`, and :func:`parse_bool`
reproduce both faithfully so the FailToAlign* error assertions match.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.config import UiElement

# strconv.ParseBool accepts exactly these tokens (true/false case variants only).
_TRUE_TOKENS = frozenset({"1", "t", "T", "TRUE", "true", "True"})
_FALSE_TOKENS = frozenset({"0", "f", "F", "FALSE", "false", "False"})

# strconv.ParseInt(s, 10, 64): optional sign then base-10 digits, nothing else.
_INT_RE = re.compile(r"^[+-]?[0-9]+$")


def parse_bool(value: str) -> bool:
    """Parse ``value`` like Go's ``strconv.ParseBool`` (same tokens + error)."""
    if value in _TRUE_TOKENS:
        return True
    if value in _FALSE_TOKENS:
        return False
    raise ValueError(f'strconv.ParseBool: parsing "{value}": invalid syntax')


def parse_int(value: str) -> int:
    """Parse ``value`` like Go's ``strconv.ParseInt(value, 10, 64)``.

    Accepts an optional leading sign and base-10 digits only — no surrounding
    whitespace, underscores, or ``0x`` prefixes (unlike Python's ``int``). A
    failure raises with Go's exact message.
    """
    if not _INT_RE.match(value):
        raise ValueError(f'strconv.ParseInt: parsing "{value}": invalid syntax')
    return int(value)


def parse_float(value: str) -> float:
    """Parse ``value`` like Go's ``strconv.ParseFloat(value, 64)``.

    Python's ``float`` accepts the same numeric forms Go does (incl. exponents
    and ``inf``/``nan``) but also tolerates surrounding whitespace; strip-free
    parsing keeps us aligned, and a failure raises Go's exact message.
    """
    if value != value.strip() or value == "":
        raise ValueError(f'strconv.ParseFloat: parsing "{value}": invalid syntax')
    try:
        return float(value)
    except ValueError as err:
        raise ValueError(f'strconv.ParseFloat: parsing "{value}": invalid syntax') from err


def align_int64_list(new_value: str) -> list[int]:
    """Split ``new_value`` on ``\\n`` and parse each line as an int (alignInt64List).

    An empty input yields an empty list; any unparseable line raises with Go's
    ParseInt error message.
    """
    if not new_value:
        return []
    return [parse_int(line) for line in new_value.split("\n")]


def align_bool_list(new_value: str) -> list[bool]:
    """Split ``new_value`` on ``\\n`` and parse each line as a bool (alignBoolList)."""
    if not new_value:
        return []
    return [parse_bool(line) for line in new_value.split("\n")]


def align_float64_list(new_value: str) -> list[float]:
    """Split ``new_value`` on ``\\n`` and parse each line as a float (alignFloat64List)."""
    if not new_value:
        return []
    return [parse_float(line) for line in new_value.split("\n")]


def align_list_list(new_value: str) -> list[list[Any]]:
    """Split ``new_value`` on ``\\n``; JSON-decode each line as a list (alignListList).

    Each line must decode to a JSON array; a non-array or malformed line raises
    (Go returns the json.Unmarshal error).
    """
    if not new_value:
        return []
    out: list[list[Any]] = []
    for line in new_value.split("\n"):
        decoded = json.loads(line)
        if not isinstance(decoded, list):
            raise ValueError(f"json: cannot unmarshal into a list: {line!r}")
        out.append(decoded)
    return out


def align_map_list(new_value: str) -> list[dict[str, Any]]:
    """Split ``new_value`` on ``\\n``; JSON-decode each line as a map (alignMapList).

    Each line must decode to a JSON object; a non-object or malformed line raises.
    """
    if not new_value:
        return []
    out: list[dict[str, Any]] = []
    for line in new_value.split("\n"):
        decoded = json.loads(line)
        if not isinstance(decoded, dict):
            raise ValueError(f"json: cannot unmarshal into a map: {line!r}")
        out.append(decoded)
    return out


def interface_to_string(value: Any) -> str:
    """Render a decoded value back to its string form (interfaceToString).

    Mirrors Go's switch: a string is returned as-is; a whole-number float renders
    as an integer (``8080`` not ``8080.0``) and any other float without a trailing
    zero; a bool renders lowercase; a list joins its (recursively rendered) items
    with ``\\n``; anything else falls back to ``str`` (Go's ``%v``).

    ``bool`` is checked before ``int``/``float`` because Python ``bool`` subclasses
    ``int`` (Go has a distinct ``case bool``).
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return repr(value)
    if isinstance(value, list):
        return "\n".join(interface_to_string(item) for item in value)
    return str(value)


def align_best_guess_list(new_value: str) -> Any:
    """Infer a typed list from a ``\\n``-separated value (alignBestGuessList).

    Best-guesses the FIRST line's scalar type and dispatches the whole value to
    the matching ``align*List`` coercer. If the first line best-guesses to a plain
    string (or the input is empty), the raw split list of strings is returned.

    ``bool`` is checked before ``int`` (Python ``bool`` subclasses ``int``).
    """
    if not new_value:
        return []
    new_list = new_value.split("\n")
    best_guess = align_best_guess(new_list[0])
    if isinstance(best_guess, bool):
        return align_bool_list(new_value)
    if isinstance(best_guess, int):
        return align_int64_list(new_value)
    if isinstance(best_guess, float):
        return align_float64_list(new_value)
    if isinstance(best_guess, list):
        return align_list_list(new_value)
    if isinstance(best_guess, dict):
        return align_map_list(new_value)
    return new_list


def zero_for_type(typ: str) -> Any:
    """Return the zero value for a forcedType (zeroForType).

    Used when an OPTIONAL ui-element field fails to coerce — the field is reset to
    its type's zero value rather than raising.
    """
    zeros: dict[str, Any] = {
        "float": 0.0,
        "int": 0,
        "bool": False,
        "string": "",
        "[]int": [],
        "[]bool": [],
        "[]float": [],
        "[]string": [],
        "[][]": [],
        "[]{}": [],
    }
    return zeros.get(typ)


def force_type(new_value: str, forced_type: str) -> Any:
    """Coerce ``new_value`` to a setting's declared ``forcedType`` (forceType).

    Dispatches on the forcedType string: scalar (``float``/``int``/``bool``/
    ``string``) via the ``parse_*`` helpers, and list (``[]int``/``[]bool``/
    ``[]float``/``[]string``/``[][]``/``[]{}``) via the ``align*List`` coercers.
    An unknown forcedType raises (Go's "Unsupported forced type").
    """
    if forced_type == "float":
        return parse_float(new_value)
    if forced_type == "int":
        return parse_int(new_value)
    if forced_type == "bool":
        return parse_bool(new_value)
    if forced_type == "string":
        return new_value
    if forced_type == "[]int":
        return align_int64_list(new_value)
    if forced_type == "[]bool":
        return align_bool_list(new_value)
    if forced_type == "[]float":
        return align_float64_list(new_value)
    if forced_type == "[]string":
        if new_value:
            return new_value.split("\n")
        return []
    if forced_type == "[][]":
        return align_list_list(new_value)
    if forced_type == "[]{}":
        return align_map_list(new_value)
    raise ValueError("Unsupported forced type: " + forced_type)


def coerce_map_list_field_types(
    list_: list[dict[str, Any]], ui_elements: list[UiElement]
) -> list[dict[str, Any]]:
    """Coerce each map's typed fields per its UI element schema (coerceMapListFieldTypes).

    For every map in ``list_`` and every ui-element with a ``forced_type`` AND a
    ``field`` set, if the field is present its value is rendered to a string and
    re-coerced to the declared type. A coercion failure on a REQUIRED field raises;
    on an optional field the field is reset to its type's zero value.
    """
    for m in list_:
        for ui_element in ui_elements:
            if ui_element.forced_type == "" or ui_element.field == "":
                continue
            if ui_element.field not in m:
                continue
            try:
                coerced = force_type(
                    interface_to_string(m[ui_element.field]), ui_element.forced_type
                )
            except ValueError as err:
                if ui_element.required:
                    raise ValueError(f'field "{ui_element.field}": {err}') from err
                coerced = zero_for_type(ui_element.forced_type)
            m[ui_element.field] = coerced
    return list_


def align_best_guess(new_value: str) -> Any:
    """Guess a type for a value with no existing type to match (alignBestGuess).

    Tries, in order: int, float, bool, then a ``\\n``-separated list
    (:func:`align_best_guess_list`), then a JSON object (``{...}``) or array
    (``[...]``); failing all of those, the string is returned unchanged. A JSON
    decode failure falls through to the next branch (matching Go's discarded
    error), so a non-JSON ``{...}`` string stays a string.
    """
    try:
        return parse_int(new_value)
    except ValueError:
        pass
    try:
        return parse_float(new_value)
    except ValueError:
        pass
    try:
        return parse_bool(new_value)
    except ValueError:
        pass

    if "\n" in new_value:
        return align_best_guess_list(new_value)

    if new_value.startswith("{") and new_value.endswith("}"):
        try:
            return json.loads(new_value)
        except ValueError:
            pass
    if new_value.startswith("[") and new_value.endswith("]"):
        try:
            return json.loads(new_value)
        except ValueError:
            pass

    return new_value


def align_type(old_value: Any, new_value: str) -> Any:
    """Coerce ``new_value`` to match the type of ``old_value`` (alignType).

    Scalar dispatch (this unit):
      * ``bool`` old  -> :func:`parse_bool`
      * ``int`` old   -> :func:`parse_int`
      * ``float`` old -> :func:`parse_float`

    Go's alignType has NO ``case string``; a ``str`` (or ``None``, or any other
    unhandled scalar) ``old_value`` falls through to the trailing
    ``return alignBestGuess(newValue)``, so we route those to
    :func:`align_best_guess` (e.g. a numeric-looking string becomes an int).

    List dispatch (``list`` old): Go distinguishes ``[]interface{}``/``[]string``/
    ``[]int64``/``[]bool``/``[]float64``, but ``yaml.safe_load`` and
    :func:`align_best_guess_list` only ever produce a plain Python ``list``. We
    unify those Go cases here — an EMPTY old list best-guesses the new value as a
    list; otherwise we dispatch on the type of the FIRST element (bool→bool list,
    int→int list, float→float list, str→raw ``split("\\n")`` Go ``[]string`` case,
    list→list-of-list, dict→map-list, else→best-guess list).

    Note: ``bool`` is checked before ``int`` (in both the old-value scalar dispatch
    and the first-element list dispatch) because Python ``bool`` is a subclass of
    ``int`` (Go has distinct types and an explicit ``case bool``).
    """
    if old_value is not None:
        # bool must precede int: in Python bool is an int subclass.
        if isinstance(old_value, bool):
            return parse_bool(new_value)
        if isinstance(old_value, int):
            return parse_int(new_value)
        if isinstance(old_value, float):
            return parse_float(new_value)
        if isinstance(old_value, list):
            if len(old_value) == 0:
                return align_best_guess_list(new_value)
            first = old_value[0]
            if isinstance(first, bool):
                return align_bool_list(new_value)
            if isinstance(first, int):
                return align_int64_list(new_value)
            if isinstance(first, float):
                return align_float64_list(new_value)
            if isinstance(first, str):
                # Go's []string case: a verbatim newline split (no parsing).
                return new_value.split("\n")
            if isinstance(first, list):
                return align_list_list(new_value)
            if isinstance(first, dict):
                return align_map_list(new_value)
            return align_best_guess_list(new_value)
    # str / None / any unhandled scalar -> Go's trailing alignBestGuess(newValue).
    return align_best_guess(new_value)
