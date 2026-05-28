"""Setting domain model — ported from Go model/config.go."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

_MINION_ID_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")
_SETTING_ID_RE = re.compile(r"^[a-zA-Z0-9*/:\-_.]+$")


def is_valid_minion_id(id: str) -> bool:
    """Return True if id contains only alphanumeric, hyphen, underscore, dot."""
    return bool(_MINION_ID_RE.match(id))


def is_valid_setting_id(id: str) -> bool:
    """Return True if id contains allowed chars (adds slash, colon, asterisk)."""
    return bool(_SETTING_ID_RE.match(id))


class Setting(BaseModel):
    """Represents a configuration setting."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    title: str = ""
    description: str = ""
    global_: bool = Field(default=False, alias="global")
    node: bool = False
    node_id: str = Field(default="", alias="nodeId")
    default: str = ""
    default_available: bool = Field(default=False, alias="defaultAvailable")
    value: str = ""
    multiline: bool = False
    readonly: bool = False
    readonly_ui: bool = Field(default=False, alias="readonlyUi")
    sensitive: bool = False
    regex: str = ""
    regex_failure_message: str = Field(default="", alias="regexFailureMessage")
    required: bool = False
    file: bool = False
    advanced: bool = False
    help_link: str = Field(default="", alias="helpLink")
    syntax: str = ""
    forced_type: str = Field(default="", alias="forcedType")
    duplicates: bool = False
    jinja_escaped: bool = Field(default=False, alias="jinjaEscaped")
    options: list[str] = Field(default_factory=list)
    option_separator: str = Field(default="", alias="optionSeparator")

    def is_duplicated_setting(self) -> bool:
        """Assume descriptionless settings are duplicated."""
        return len(self.description) == 0

    def supports_jinja(self) -> bool:
        """Return True if this setting can contain Jinja2 escape characters."""
        return self.syntax != "json" and (self.jinja_escaped or self.is_duplicated_setting())


def new_setting(id: str) -> Setting:
    """Factory matching Go's NewSetting."""
    return Setting(id=id)
