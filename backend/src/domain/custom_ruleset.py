"""CustomRuleset domain model — ported from Go model/custom_ruleset.go."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CustomRuleset(BaseModel):
    """Represents a custom ruleset configuration."""

    model_config = ConfigDict(populate_by_name=True)

    community: bool = False
    license: str = ""
    url: str = ""
    target_file: str = Field(default="", alias="target-file")
    file: str = ""
    ruleset: str = ""


def _parse_community(value: Any) -> bool:
    """Parse a community flag from various types, matching Go's switch behavior."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("1", "true", "t", "yes", "y")
    return False


def get_custom_rulesets_default(
    cfg: dict[str, Any],
    field: str,
    dflt: list[CustomRuleset],
) -> tuple[list[CustomRuleset] | None, str | None]:
    """Parse custom rulesets from config dict. Returns (rulesets, error_string).

    If the field is missing or None in config, returns the defaults.
    """
    if field not in cfg or cfg[field] is None:
        return dflt, None

    cfg_inter = cfg[field]
    if not isinstance(cfg_inter, list):
        return None, f'top level config value "{field}" is not an array of objects'

    rulesets: list[CustomRuleset] = []
    for item in cfg_inter:
        if not isinstance(item, dict):
            return None, f'"{field}" entry is not an object'

        file_val = item.get("file", "")
        if not isinstance(file_val, str):
            file_val = ""
        url_val = item.get("url", "")
        if not isinstance(url_val, str):
            url_val = ""
        target_val = item.get("target-file", "")
        if not isinstance(target_val, str):
            target_val = ""

        if not file_val and not url_val and not target_val:
            return None, f'missing "file" or "url"+"target-file" from "{field}" entry'

        if url_val and not target_val:
            return None, f'missing "target-file" from "{field}" entry'
        if target_val and not url_val:
            return None, f'missing "url" from "{field}" entry'

        ruleset = item.get("ruleset")
        if not isinstance(ruleset, str):
            return None, f'missing "ruleset" from "{field}" entry'

        license_val = item.get("license")
        if not isinstance(license_val, str):
            return None, f'missing "license" from "{field}" entry'

        community = _parse_community(item.get("community"))

        r = CustomRuleset(
            file=file_val,
            url=url_val,
            target_file=target_val,
            license=license_val,
            community=community,
            ruleset=ruleset,
        )

        rulesets.append(r)

    return rulesets, None
