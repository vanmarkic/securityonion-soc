"""Repo domain model — ported from Go model/repo.go."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Repo(BaseModel):
    """Represents a rules repository configuration."""

    model_config = ConfigDict(populate_by_name=True)

    repo_url: str = Field(default="", alias="repo")
    branch: str | None = None
    license: str = ""
    folder: str | None = None
    community: bool = False
    ruleset_name: str = ""


def _parse_community(value: Any) -> bool:
    """Parse a community flag from various types, matching Go's switch behavior."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("1", "true", "t", "yes", "y")
    return False


def get_repos_default(
    cfg: dict[str, Any],
    field: str,
    license_required: bool,
    dflt: list[Repo],
) -> tuple[list[Repo], str | None]:
    """Parse repo list from config dict. Returns (repos, error_string).

    If the field is missing from config, returns the defaults.
    """
    if field not in cfg:
        return dflt, None

    cfg_inter = cfg[field]
    if not isinstance(cfg_inter, list):
        return None, f'top level config value "{field}" is not an array of objects'

    repos: list[Repo] = []
    for item in cfg_inter:
        if not isinstance(item, dict):
            return None, f'"{field}" entry is not an object'

        repo_url = item.get("repo")
        if not isinstance(repo_url, str):
            return None, f'missing "repo" link from "{field}" entry'

        license_val = item.get("license")
        if not isinstance(license_val, str) and license_required:
            return None, f'missing "license" from "{field}" entry'
        if license_val is None:
            license_val = ""

        community = _parse_community(item.get("community"))
        ruleset_name = item.get("rulesetName", "")
        if not isinstance(ruleset_name, str):
            ruleset_name = ""

        r = Repo(
            repo_url=repo_url,
            license=license_val,
            community=community,
            ruleset_name=ruleset_name,
        )

        folder = item.get("folder")
        if isinstance(folder, str):
            r.folder = folder

        repos.append(r)

    return repos, None
