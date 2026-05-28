"""Tests for Detection domain models -- ported from Go model/detection_test.go."""

import pytest

from src.domain.detection import (
    Detection,
    Override,
    OverrideParameters,
    EngineName,
    OverrideType,
    Severity,
    SigLanguage,
)


# ---------------------------------------------------------------------------
# TestDetectionOverrideValidate — table-driven, ported 1:1 from Go
# ---------------------------------------------------------------------------

class TestDetectionOverrideValidate:
    """Port of Go's TestDetectionOverrideValidate (all 35 sub-tests)."""

    # -- Valid detections (no overrides) --

    def test_valid_suricata_detection(self):
        d = Detection(engine=EngineName.SURICATA)
        d.validate()

    def test_valid_elastalert_detection(self):
        d = Detection(engine=EngineName.ELASTALERT)
        d.validate()

    def test_valid_strelka_detection(self):
        d = Detection(engine=EngineName.STRELKA)
        d.validate()

    def test_invalid_detection_engine(self):
        d = Detection(engine="invalid")
        with pytest.raises(ValueError, match="unsupported engine"):
            d.validate()

    # -- Valid Suricata overrides --

    def test_valid_suricata_override(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.MODIFY,
                    override_parameters=OverrideParameters(
                        regex=".*", value="test",
                    ),
                ),
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="0.0.0.0", track="by_src",
                    ),
                ),
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="limit",
                        track="by_src",
                        count=1,
                        seconds=60,
                    ),
                ),
            ],
        )
        d.validate()

    # -- Invalid Suricata Modify overrides --

    def test_invalid_suricata_modify_override_missing(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.MODIFY,
                    override_parameters=OverrideParameters(),
                ),
            ],
        )
        with pytest.raises(ValueError, match="missing required parameter"):
            d.validate()

    def test_invalid_suricata_modify_override_extra(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.MODIFY,
                    override_parameters=OverrideParameters(
                        regex=".*", value="test", count=1,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="unnecessary fields in override"):
            d.validate()

    def test_invalid_suricata_modify_override_invalid_regex(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.MODIFY,
                    override_parameters=OverrideParameters(
                        regex="[invalid", value="test",
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid regex pattern"):
            d.validate()

    # -- Invalid Suricata Suppress overrides --

    def test_invalid_suricata_suppress_override_missing(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(),
                ),
            ],
        )
        with pytest.raises(ValueError, match="missing required parameter"):
            d.validate()

    def test_invalid_suricata_suppress_override_extra(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="0.0.0.0", track="by_src", count=1,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="unnecessary fields in override"):
            d.validate()

    def test_invalid_suricata_suppress_override_invalid_track_by_both(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="192.168.1.1/32", track="by_both",
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid track value"):
            d.validate()

    def test_invalid_suricata_suppress_override_invalid_track_garbage(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="192.168.1.1/32", track="invalid",
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid track value"):
            d.validate()

    def test_invalid_suricata_suppress_override_invalid_ip_malformed(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="not-an-ip", track="by_src",
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid IP address"):
            d.validate()

    def test_invalid_suricata_suppress_override_invalid_ip_bad_cidr(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="192.168.1.0/99", track="by_src",
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid CIDR"):
            d.validate()

    def test_valid_suricata_suppress_override_plain_ip(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="192.168.1.1", track="by_src",
                    ),
                ),
            ],
        )
        d.validate()

    def test_valid_suricata_suppress_override_cidr(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="192.168.1.0/24", track="by_dst",
                    ),
                ),
            ],
        )
        d.validate()

    def test_valid_suricata_suppress_override_variable(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="$HOME_NET", track="by_either",
                    ),
                ),
            ],
        )
        d.validate()

    def test_valid_suricata_suppress_override_bracketed_list(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(
                        ip="[192.168.1.1,10.0.0.0/8]", track="by_src",
                    ),
                ),
            ],
        )
        d.validate()

    # -- Invalid Suricata Threshold overrides --

    def test_invalid_suricata_threshold_override_missing(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(),
                ),
            ],
        )
        with pytest.raises(ValueError, match="missing required parameter"):
            d.validate()

    def test_invalid_suricata_threshold_override_extra(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="limit",
                        track="by_src",
                        count=1,
                        seconds=60,
                        regex=".*",
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="unnecessary fields in override"):
            d.validate()

    def test_invalid_suricata_threshold_override_invalid_threshold_type(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="suppress",
                        track="by_src",
                        count=1,
                        seconds=60,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid thresholdType value"):
            d.validate()

    def test_invalid_suricata_threshold_override_invalid_track_by_either(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="limit",
                        track="by_either",
                        count=1,
                        seconds=60,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid track value"):
            d.validate()

    def test_invalid_suricata_threshold_override_count_zero(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="limit",
                        track="by_src",
                        count=0,
                        seconds=60,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid count value"):
            d.validate()

    def test_invalid_suricata_threshold_override_count_negative(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="limit",
                        track="by_src",
                        count=-1,
                        seconds=60,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid count value"):
            d.validate()

    def test_invalid_suricata_threshold_override_seconds_zero(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="limit",
                        track="by_src",
                        count=1,
                        seconds=0,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid seconds value"):
            d.validate()

    def test_invalid_suricata_threshold_override_seconds_negative(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="limit",
                        track="by_src",
                        count=1,
                        seconds=-60,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid seconds value"):
            d.validate()

    def test_valid_suricata_threshold_override_by_both_track(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type=OverrideType.THRESHOLD,
                    override_parameters=OverrideParameters(
                        threshold_type="both",
                        track="by_both",
                        count=5,
                        seconds=120,
                    ),
                ),
            ],
        )
        d.validate()

    # -- ElastAlert overrides --

    def test_valid_elastalert_override(self):
        d = Detection(
            engine=EngineName.ELASTALERT,
            overrides=[
                Override(
                    type=OverrideType.CUSTOM_FILTER,
                    override_parameters=OverrideParameters(
                        custom_filter="k: v",
                    ),
                ),
            ],
        )
        d.validate()

    def test_invalid_elastalert_custom_filter_missing(self):
        d = Detection(
            engine=EngineName.ELASTALERT,
            overrides=[
                Override(
                    type=OverrideType.CUSTOM_FILTER,
                    override_parameters=OverrideParameters(),
                ),
            ],
        )
        with pytest.raises(ValueError, match="missing required parameter"):
            d.validate()

    def test_invalid_elastalert_custom_filter_extra(self):
        d = Detection(
            engine=EngineName.ELASTALERT,
            overrides=[
                Override(
                    type=OverrideType.CUSTOM_FILTER,
                    override_parameters=OverrideParameters(
                        custom_filter="k: v", count=1,
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="unnecessary fields in override"):
            d.validate()

    def test_invalid_elastalert_custom_filter_bad_yaml(self):
        d = Detection(
            engine=EngineName.ELASTALERT,
            overrides=[
                Override(
                    type=OverrideType.CUSTOM_FILTER,
                    override_parameters=OverrideParameters(
                        custom_filter="not valid yaml",
                    ),
                ),
            ],
        )
        with pytest.raises(ValueError, match="custom filter override has invalid YAML"):
            d.validate()

    def test_invalid_elastalert_override_type(self):
        d = Detection(
            engine=EngineName.ELASTALERT,
            overrides=[
                Override(
                    type=OverrideType.SUPPRESS,
                    override_parameters=OverrideParameters(),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid override type"):
            d.validate()

    def test_invalid_strelka_override_type(self):
        d = Detection(
            engine=EngineName.STRELKA,
            overrides=[
                Override(
                    type=OverrideType.MODIFY,
                    override_parameters=OverrideParameters(),
                ),
            ],
        )
        with pytest.raises(ValueError, match="invalid override type"):
            d.validate()

    def test_invalid_override_type_empty(self):
        d = Detection(
            engine=EngineName.SURICATA,
            overrides=[
                Override(
                    type="",
                    override_parameters=OverrideParameters(),
                ),
            ],
        )
        with pytest.raises(ValueError, match="override type is required"):
            d.validate()


# ---------------------------------------------------------------------------
# TestOverrideEqual — ported 1:1 from Go
# ---------------------------------------------------------------------------

class TestOverrideEqual:
    """Port of Go's TestOverrideEqual (all 11 sub-tests)."""

    def test_both_nil(self):
        assert Override.equal(None, None) is True

    def test_one_nil(self):
        o = Override(
            type=OverrideType.MODIFY,
            override_parameters=OverrideParameters(
                regex=".*", value="test",
            ),
        )
        assert Override.equal(o, None) is False
        assert Override.equal(None, o) is False

    def test_unequal_meta(self):
        one = Override(
            type=OverrideType.MODIFY,
            override_parameters=OverrideParameters(
                regex=".*", value="test",
            ),
        )
        two = Override(
            type=OverrideType.SUPPRESS,
            override_parameters=OverrideParameters(
                ip="0.0.0.0", track="by_src",
            ),
        )
        assert Override.equal(one, two) is False
        assert Override.equal(two, one) is False

    def test_equal_modify(self):
        one = Override(
            type=OverrideType.MODIFY,
            override_parameters=OverrideParameters(
                regex=".*", value="test",
            ),
        )
        two = Override(
            type=OverrideType.MODIFY,
            override_parameters=OverrideParameters(
                regex=".*", value="test",
            ),
        )
        assert Override.equal(one, two) is True
        assert Override.equal(two, one) is True

    def test_unequal_modify(self):
        one = Override(
            type=OverrideType.MODIFY,
            override_parameters=OverrideParameters(
                regex=".+", value="Hello World",
            ),
        )
        two = Override(
            type=OverrideType.MODIFY,
            override_parameters=OverrideParameters(
                regex=".*", value="test",
            ),
        )
        assert Override.equal(one, two) is False
        assert Override.equal(two, one) is False

    def test_equal_suppress(self):
        one = Override(
            type=OverrideType.SUPPRESS,
            override_parameters=OverrideParameters(
                ip="0.0.0.0", track="by_src",
            ),
        )
        two = Override(
            type=OverrideType.SUPPRESS,
            override_parameters=OverrideParameters(
                ip="0.0.0.0", track="by_src",
            ),
        )
        assert Override.equal(one, two) is True
        assert Override.equal(two, one) is True

    def test_unequal_suppress(self):
        one = Override(
            type=OverrideType.SUPPRESS,
            override_parameters=OverrideParameters(
                ip="0.0.0.0", track="by_src",
            ),
        )
        two = Override(
            type=OverrideType.SUPPRESS,
            override_parameters=OverrideParameters(
                ip="127.0.0.1", track="by_either",
            ),
        )
        assert Override.equal(one, two) is False
        assert Override.equal(two, one) is False

    def test_equal_threshold(self):
        one = Override(
            type=OverrideType.THRESHOLD,
            override_parameters=OverrideParameters(
                threshold_type="limit", track="by_src", count=3, seconds=60,
            ),
        )
        two = Override(
            type=OverrideType.THRESHOLD,
            override_parameters=OverrideParameters(
                threshold_type="limit", track="by_src", count=3, seconds=60,
            ),
        )
        assert Override.equal(one, two) is True
        assert Override.equal(two, one) is True

    def test_unequal_threshold(self):
        one = Override(
            type=OverrideType.THRESHOLD,
            override_parameters=OverrideParameters(
                threshold_type="both", track="by_src", count=1, seconds=180,
            ),
        )
        two = Override(
            type=OverrideType.THRESHOLD,
            override_parameters=OverrideParameters(
                threshold_type="limit", track="by_dst", count=3, seconds=60,
            ),
        )
        assert Override.equal(one, two) is False
        assert Override.equal(two, one) is False

    def test_equal_custom_filter(self):
        one = Override(
            type=OverrideType.CUSTOM_FILTER,
            override_parameters=OverrideParameters(
                custom_filter="k: v",
            ),
        )
        two = Override(
            type=OverrideType.CUSTOM_FILTER,
            override_parameters=OverrideParameters(
                custom_filter="k: v",
            ),
        )
        assert Override.equal(one, two) is True
        assert Override.equal(two, one) is True

    def test_unequal_custom_filter(self):
        one = Override(
            type=OverrideType.CUSTOM_FILTER,
            override_parameters=OverrideParameters(
                custom_filter="k: v",
            ),
        )
        two = Override(
            type=OverrideType.CUSTOM_FILTER,
            override_parameters=OverrideParameters(
                custom_filter="k2: v2",
            ),
        )
        assert Override.equal(one, two) is False
        assert Override.equal(two, one) is False


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------

class TestEnumValues:
    """Verify enum string values match Go constants."""

    def test_severity_values(self):
        assert Severity.UNKNOWN == "unknown"
        assert Severity.INFORMATIONAL == "informational"
        assert Severity.LOW == "low"
        assert Severity.MEDIUM == "medium"
        assert Severity.HIGH == "high"
        assert Severity.CRITICAL == "critical"

    def test_engine_name_values(self):
        assert EngineName.SURICATA == "suricata"
        assert EngineName.STRELKA == "strelka"
        assert EngineName.ELASTALERT == "elastalert"

    def test_sig_language_values(self):
        assert SigLanguage.SIGMA == "sigma"
        assert SigLanguage.SURICATA == "suricata"
        assert SigLanguage.YARA == "yara"

    def test_override_type_values(self):
        assert OverrideType.SUPPRESS == "suppress"
        assert OverrideType.THRESHOLD == "threshold"
        assert OverrideType.MODIFY == "modify"
        assert OverrideType.CUSTOM_FILTER == "customFilter"
