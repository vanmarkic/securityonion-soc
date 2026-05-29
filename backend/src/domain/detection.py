"""Detection domain models -- ported from Go model/detection.go."""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from enum import StrEnum

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.domain.case import Auditable

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ScanType(StrEnum):
    FILES = "files"
    PACKETS = "packets"
    PACKETS_AND_FILES = "files,packets"
    ELASTIC = "elastic"


class SigLanguage(StrEnum):
    SIGMA = "sigma"
    SURICATA = "suricata"
    YARA = "yara"


class Severity(StrEnum):
    UNKNOWN = "unknown"
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IDType(StrEnum):
    UUID = "uuid"
    SID = "sid"


class EngineName(StrEnum):
    SURICATA = "suricata"
    STRELKA = "strelka"
    ELASTALERT = "elastalert"


class OverrideType(StrEnum):
    SUPPRESS = "suppress"
    THRESHOLD = "threshold"
    MODIFY = "modify"
    CUSTOM_FILTER = "customFilter"


# Track constants
TRACK_BY_SRC = "by_src"
TRACK_BY_DST = "by_dst"
TRACK_BY_EITHER = "by_either"  # suppress only
TRACK_BY_BOTH = "by_both"  # threshold only

# ThresholdType constants
THRESHOLD_TYPE_LIMIT = "limit"
THRESHOLD_TYPE_THRESHOLD = "threshold"
THRESHOLD_TYPE_BOTH = "both"

# License constants
LICENSE_DRL = "DRL"
LICENSE_COMMERCIAL = "Commercial"
LICENSE_BSD = "BSD"
LICENSE_UNKNOWN = "Unknown"

# Supported engines registry (mirrors Go's EnginesByName)
ENGINES_BY_NAME: dict[str, EngineName] = {
    EngineName.SURICATA: EngineName.SURICATA,
    EngineName.STRELKA: EngineName.STRELKA,
    EngineName.ELASTALERT: EngineName.ELASTALERT,
}


# ---------------------------------------------------------------------------
# IP validation (mirrors Go's validateSuricataIP / validateSingleIP)
# ---------------------------------------------------------------------------

def _validate_single_ip(ip: str) -> None:
    """Validate a single IP or CIDR notation."""
    if "/" in ip:
        try:
            ipaddress.ip_network(ip, strict=False)
        except ValueError:
            raise ValueError(f"invalid CIDR {ip!r}") from None
        return

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError(f"invalid IP address {ip!r}") from None


def _validate_suricata_ip(ip: str) -> None:
    """Validate IP format for Suricata suppress rules.

    Valid formats: plain IP (1.2.3.4), CIDR (1.2.3.0/24),
    variable ($HOME_NET), or bracketed list ([1.2.3.4,5.6.7.8/24]).
    """
    if not ip:
        raise ValueError("ip value cannot be empty")

    # Allow Suricata variables like $HOME_NET
    if ip.startswith("$"):
        return

    # Handle bracketed list format [ip1,ip2,...]
    if ip.startswith("[") and ip.endswith("]"):
        inner = ip[1:-1]
        parts = inner.split(",")
        for part in parts:
            part = part.strip()
            _validate_single_ip(part)
        return

    _validate_single_ip(ip)


# ---------------------------------------------------------------------------
# Override parameters & Override
# ---------------------------------------------------------------------------

class OverrideParameters(BaseModel):
    """Parameters for a detection override, varies by override type."""

    model_config = ConfigDict(populate_by_name=True)

    # modify (suricata only)
    regex: str | None = None
    value: str | None = None

    # threshold (suricata only)
    threshold_type: str | None = Field(default=None, alias="thresholdType")

    # suppress + threshold (suricata only)
    track: str | None = None

    # suppress (suricata only)
    ip: str | None = None

    # threshold (suricata only)
    count: int | None = None
    seconds: int | None = None

    # customFilter (elastalert only)
    custom_filter: str | None = Field(default=None, alias="customFilter")


class Override(BaseModel):
    """A tuning override applied to a detection."""

    model_config = ConfigDict(populate_by_name=True)

    type: str = ""
    is_enabled: bool = Field(default=False, alias="isEnabled")
    note: str = ""
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    override_parameters: OverrideParameters = Field(
        default_factory=OverrideParameters,
        alias="overrideParameters",
    )

    def validate_override(self, engine: str) -> None:
        """Validate this override against the given engine's rules."""
        if not self.type:
            raise ValueError("override type is required")

        p = self.override_parameters

        if engine == EngineName.SURICATA:
            self._validate_suricata(p)
        elif engine == EngineName.ELASTALERT:
            self._validate_elastalert(p)
        else:
            raise ValueError("invalid override type")

    def _validate_suricata(self, p: OverrideParameters) -> None:
        if self.type == OverrideType.MODIFY:
            if p.regex is None or p.value is None:
                raise ValueError("missing required parameter(s)")

            # Validate regex compiles
            try:
                re.compile(p.regex)
            except re.error as exc:
                raise ValueError(f"invalid regex pattern: {exc}") from exc

            if (
                p.threshold_type is not None
                or p.track is not None
                or p.count is not None
                or p.seconds is not None
                or p.custom_filter is not None
            ):
                raise ValueError("unnecessary fields in override")

        elif self.type == OverrideType.SUPPRESS:
            if p.ip is None or p.track is None:
                raise ValueError("missing required parameter(s)")

            if (
                p.regex is not None
                or p.value is not None
                or p.threshold_type is not None
                or p.count is not None
                or p.seconds is not None
                or p.custom_filter is not None
            ):
                raise ValueError("unnecessary fields in override")

            # Validate track (suppress allows by_either, not by_both)
            if p.track not in (TRACK_BY_SRC, TRACK_BY_DST, TRACK_BY_EITHER):
                raise ValueError(
                    f"invalid track value {p.track!r}: "
                    "must be by_src, by_dst, or by_either"
                )

            _validate_suricata_ip(p.ip)

        elif self.type == OverrideType.THRESHOLD:
            if (
                p.threshold_type is None
                or p.track is None
                or p.count is None
                or p.seconds is None
            ):
                raise ValueError("missing required parameter(s)")

            if (
                p.regex is not None
                or p.value is not None
                or p.custom_filter is not None
            ):
                raise ValueError("unnecessary fields in override")

            # Validate threshold_type
            if p.threshold_type not in (
                THRESHOLD_TYPE_LIMIT,
                THRESHOLD_TYPE_THRESHOLD,
                THRESHOLD_TYPE_BOTH,
            ):
                raise ValueError(
                    f"invalid thresholdType value {p.threshold_type!r}: "
                    "must be limit, threshold, or both"
                )

            # Validate track (threshold allows by_both, not by_either)
            if p.track not in (TRACK_BY_SRC, TRACK_BY_DST, TRACK_BY_BOTH):
                raise ValueError(
                    f"invalid track value {p.track!r}: "
                    "must be by_src, by_dst, or by_both"
                )

            # Count must be positive
            if p.count <= 0:
                raise ValueError(
                    f"invalid count value {p.count}: must be greater than 0"
                )

            # Seconds must be positive
            if p.seconds <= 0:
                raise ValueError(
                    f"invalid seconds value {p.seconds}: must be greater than 0"
                )

    def _validate_elastalert(self, p: OverrideParameters) -> None:
        if self.type == OverrideType.CUSTOM_FILTER:
            if p.custom_filter is None:
                raise ValueError("missing required parameter(s)")

            if (
                p.regex is not None
                or p.value is not None
                or p.threshold_type is not None
                or p.track is not None
                or p.count is not None
                or p.seconds is not None
            ):
                raise ValueError("unnecessary fields in override")

            # Replace tabs with spaces (like Go's TabsToSpaces)
            filter_text = p.custom_filter.replace("\t", "  ")
            p.custom_filter = filter_text

            # Validate YAML parses to a mapping
            try:
                result = yaml.safe_load(filter_text)
            except yaml.YAMLError as exc:
                raise ValueError(
                    f"custom filter override has invalid YAML: {exc}"
                ) from exc

            if not isinstance(result, dict):
                raise ValueError(
                    "custom filter override has invalid YAML: "
                    "value must be a YAML mapping"
                )
        else:
            raise ValueError("invalid override type")

    @staticmethod
    def equal(one: Override | None, two: Override | None) -> bool:
        """Compare two overrides for equality (mirrors Go's Override.Equal)."""
        if one is None and two is None:
            return True
        if one is None or two is None:
            return False
        if (
            one.type != two.type
            or one.is_enabled != two.is_enabled
            or one.created_at != two.created_at
            or one.updated_at != two.updated_at
        ):
            return False

        p1 = one.override_parameters
        p2 = two.override_parameters

        if one.type == OverrideType.SUPPRESS:
            return p1.ip == p2.ip and p1.track == p2.track
        elif one.type == OverrideType.THRESHOLD:
            return (
                p1.threshold_type == p2.threshold_type
                and p1.track == p2.track
                and p1.count == p2.count
                and p1.seconds == p2.seconds
            )
        elif one.type == OverrideType.MODIFY:
            return p1.regex == p2.regex and p1.value == p2.value
        elif one.type == OverrideType.CUSTOM_FILTER:
            return p1.custom_filter == p2.custom_filter

        return False


# ---------------------------------------------------------------------------
# AiFields
# ---------------------------------------------------------------------------

class AiFields(BaseModel):
    """AI-generated description fields for a detection."""

    model_config = ConfigDict(populate_by_name=True)

    ai_summary: str = Field(default="", alias="aiSummary")
    ai_summary_reviewed: bool = Field(default=False, alias="aiSummaryReviewed")
    is_ai_summary_stale: bool = Field(default=False, alias="isSummaryStale")


# ---------------------------------------------------------------------------
# DetectionComment
# ---------------------------------------------------------------------------

class DetectionComment(Auditable):
    """A comment attached to a detection."""

    detection_id: str = Field(default="", alias="detectionId")
    value: str = ""


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

class Detection(Auditable):
    """Represents a Security Onion detection rule."""

    model_config = ConfigDict(populate_by_name=True)

    public_id: str = Field(default="", alias="publicId")
    title: str = ""
    severity: str = Severity.UNKNOWN
    author: str = ""
    category: str = ""
    description: str = ""
    content: str = ""
    is_enabled: bool = Field(default=False, alias="isEnabled")
    is_reporting: bool = Field(default=False, alias="isReporting")
    is_community: bool = Field(default=False, alias="isCommunity")
    engine: str = ""
    language: str = ""
    overrides: list[Override] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ruleset: str = ""
    license: str = ""
    source_created: datetime | None = Field(default=None, alias="sourceCreated")
    source_updated: datetime | None = Field(default=None, alias="sourceUpdated")
    product: str = ""
    service: str = ""
    ai_fields: AiFields | None = Field(default=None, alias="aiFields")

    def validate(self) -> None:
        """Validate the detection and all its overrides.

        Mirrors Go's Detection.Validate().
        """
        self.engine = self.engine.lower()

        if self.engine not in ENGINES_BY_NAME:
            raise ValueError("unsupported engine")

        for override in self.overrides:
            override.validate_override(self.engine)
