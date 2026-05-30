"""Setting value type coercion — ported from server/modules/salt/saltstore.go.

When a setting is written back into a pillar YAML map its string value must be
coerced to the right Python type so the re-serialized YAML keeps the original
shape (an int stays an int, a bool stays a bool, etc.). Two entry points mirror
the Go store:

* :func:`align_best_guess` — used for brand-new values (no existing type to
  match): guess int, then float, then bool, else keep the string.
* :func:`align_type` — used when an existing value is present: coerce the new
  string to the SAME type as the old value (parse failures surface as errors).

Only the SCALAR branches are implemented in this unit. The LIST branches
(``[]int`` / ``[]bool`` / ``[]float`` / ``[][]`` / ``[]{}``) — Go's
alignInt64List / alignBoolList / alignFloat64List / alignListList / alignMapList
and the alignBestGuessList dispatch — are deferred to the next unit and stubbed
with ``# B2:`` markers.

Go uses ``strconv`` for parsing, whose acceptance and error strings differ from
Python's builtins; :func:`parse_int`, :func:`parse_float`, and :func:`parse_bool`
reproduce both faithfully so the FailToAlign* error assertions match.
"""

from __future__ import annotations

import re
from typing import Any

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


def align_best_guess(new_value: str) -> Any:
    """Guess a scalar type for a value with no existing type (alignBestGuess).

    Tries, in order: int, then float, then bool, else returns the string
    unchanged. The list (``\\n``-separated) and JSON object/array branches Go also
    handles here are list/structural and belong to the next unit.
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
        # B2: alignBestGuessList — \n-separated list inference.
        raise NotImplementedError("# B2: list align_best_guess (\\n-separated)")
    if (new_value.startswith("{") and new_value.endswith("}")) or (
        new_value.startswith("[") and new_value.endswith("]")
    ):
        # B2: JSON object/array best-guess decoding.
        raise NotImplementedError("# B2: json object/array align_best_guess")

    return new_value


def align_type(old_value: Any, new_value: str) -> Any:
    """Coerce ``new_value`` to match the type of ``old_value`` (alignType).

    Scalar dispatch (this unit):
      * ``bool`` old  -> :func:`parse_bool`
      * ``int`` old   -> :func:`parse_int`
      * ``float`` old -> :func:`parse_float`
      * ``str`` old   -> ``new_value`` unchanged
      * ``None`` old  -> :func:`align_best_guess`

    List dispatch (``list`` old) is deferred to the next unit (``# B2:``).

    Note: ``bool`` is checked before ``int`` because Python ``bool`` is a subclass
    of ``int`` (Go has distinct types and an explicit ``case bool``).
    """
    if old_value is not None:
        # bool must precede int: in Python bool is an int subclass.
        if isinstance(old_value, bool):
            return parse_bool(new_value)
        if isinstance(old_value, int):
            return parse_int(new_value)
        if isinstance(old_value, float):
            return parse_float(new_value)
        if isinstance(old_value, str):
            return new_value
        if isinstance(old_value, list):
            # B2: list align ([]int/[]bool/[]float/[][]/[]{} + alignBestGuessList).
            raise NotImplementedError("# B2: list align")
    return align_best_guess(new_value)
