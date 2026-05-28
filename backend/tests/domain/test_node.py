"""Tests for Node domain model — ported from Go model/node_test.go."""

import pytest

from src.domain.node import (
    NODE_STATUS_FAULT,
    NODE_STATUS_OK,
    NODE_STATUS_PENDING,
    NODE_STATUS_RESTART,
    NODE_STATUS_UNKNOWN,
    Node,
    new_node,
)


# ---------------------------------------------------------------------------
# TestSetModel
# ---------------------------------------------------------------------------

def _test_model(new_model: str, model: str, front: str, back: str) -> None:
    node = new_node("")
    node.set_model(new_model)
    assert node.model == model
    assert node.image_front == front
    assert node.image_back == back


class TestSetModel:
    def test_empty(self):
        _test_model("", "N/A", "", "")

    def test_unknown(self):
        _test_model("foo", "N/A", "", "")

    def test_sosmn(self):
        _test_model("SOSMN", "SOSMN", "sos-1u-front-thumb.jpg", "sos-1u-ethernet-back-thumb.jpg")

    def test_sos1000(self):
        _test_model("SOS1000", "SOS1000", "sos-1u-front-thumb.jpg", "sos-1u-ethernet-back-thumb.jpg")

    def test_sos500(self):
        _test_model("SOS500", "SOS500", "sos-1u-front-thumb.jpg", "sos-1u-ethernet-back-thumb.jpg")

    def test_sossnnv(self):
        _test_model("SOSSNNV", "SOSSNNV", "sos-1u-front-thumb.jpg", "sos-1u-sfp-back-thumb.jpg")

    def test_sos1000f(self):
        _test_model("SOS1000F", "SOS1000F", "sos-1u-front-thumb.jpg", "sos-1u-sfp-back-thumb.jpg")

    def test_sos10k(self):
        _test_model("SOS10K", "SOS10K", "sos-1u-front-thumb.jpg", "sos-1u-sfp-back-thumb.jpg")

    def test_sos4000(self):
        _test_model("SOS4000", "SOS4000", "sos-2u-front-thumb.jpg", "sos-2u-back-thumb.jpg")

    def test_sossn7200(self):
        _test_model("SOSSN7200", "SOSSN7200", "sos-2u-front-thumb.jpg", "sos-2u-back-thumb.jpg")

    def test_so2ami01(self):
        _test_model("SO2AMI01", "SO2AMI01", "so-cloud-aws.jpg", "")

    def test_so2azi01(self):
        _test_model("SO2AZI01", "SO2AZI01", "so-cloud-azure.jpg", "")

    def test_so2gci01(self):
        _test_model("SO2GCI01", "SO2GCI01", "so-cloud-gcp.jpg", "")

    def test_sos500_de02(self):
        _test_model("SOS500-DE02", "SOS500-DE02", "500v2_front_thumb.jpg", "500v2_back_thumb.jpg")

    def test_sosmn_de02(self):
        _test_model("SOSMN-DE02", "SOSMN-DE02", "MNv2_front_thumb.jpg", "MNv2_back_thumb.jpg")

    def test_sos1000_de02(self):
        _test_model("SOS1000-DE02", "SOS1000-DE02", "MNv2_front_thumb.jpg", "MNv2_back_thumb.jpg")

    def test_sos2000_de02(self):
        _test_model("SOS2000-DE02", "SOS2000-DE02", "MNv2_front_thumb.jpg", "MNv2_back_thumb.jpg")

    def test_sos5000_de02(self):
        _test_model("SOS5000-DE02", "SOS5000-DE02", "5000v2_front_thumb.jpg", "5000v2_back_thumb.jpg")

    def test_sossn7200_de02(self):
        _test_model("SOSSN7200-DE02", "SOSSN7200-DE02", "5000v2_front_thumb.jpg", "5000v2_back_thumb.jpg")

    def test_sos10k_de02(self):
        _test_model("SOS10K-DE02", "SOS10K-DE02", "NVv2_front_thumb.jpg", "NVv2_back_thumb.jpg")

    def test_sos10knv_de02(self):
        _test_model("SOS10KNV-DE02", "SOS10KNV-DE02", "NVv2_front_thumb.jpg", "NVv2_back_thumb.jpg")

    def test_sossnnv_de02(self):
        _test_model("SOSSNNV-DE02", "SOSSNNV-DE02", "NVv2_front_thumb.jpg", "NVv2_back_thumb.jpg")

    def test_gofast_lt_de02(self):
        _test_model("SOS-GOFAST-LT-DE02", "SOS-GOFAST-LT-DE02", "GOFASTv2_front_thumb.jpg", "GOFASTv2_back_thumb.jpg")

    def test_gofast_md_de02(self):
        _test_model("SOS-GOFAST-MD-DE02", "SOS-GOFAST-MD-DE02", "GOFASTv2_front_thumb.jpg", "GOFASTv2_back_thumb.jpg")

    def test_gofast_hv_de02(self):
        _test_model("SOS-GOFAST-HV-DE02", "SOS-GOFAST-HV-DE02", "GOFASTv2_front_thumb.jpg", "GOFASTv2_back_thumb.jpg")


# ---------------------------------------------------------------------------
# TestUpdateOverallStatus helpers
# ---------------------------------------------------------------------------

def _test_status(
    enhanced_status_enabled: bool,
    node_status: str,
    connection_status: str,
    raid_status: str,
    process_status: str,
    eventstore_status: str,
    restart_needed: int,
    expected_status: str,
) -> None:
    node = new_node("")
    node.status = node_status
    node.connection_status = connection_status
    node.raid_status = raid_status
    node.process_status = process_status
    node.eventstore_status = eventstore_status
    node.os_needs_restart = restart_needed
    result = node.update_overall_status(enhanced_status_enabled)
    should_change = node_status != expected_status
    assert result == should_change
    assert node.status == expected_status


# ---------------------------------------------------------------------------
# TestUpdateNodeStatusAllUnknown
# ---------------------------------------------------------------------------

class TestUpdateNodeStatusAllUnknown:
    def test_unknown_all_unknown(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_all_unknown(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_all_unknown(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)


# ---------------------------------------------------------------------------
# TestUpdateNodeStatusOneNotUnknown (enhanced=True)
# ---------------------------------------------------------------------------

class TestUpdateNodeStatusOneNotUnknown:
    def test_restart_needed(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 1, NODE_STATUS_FAULT)

    def test_conn_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_process_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_process_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_eventstore_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_eventstore_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)

    # With node status = OK
    def test_ok_conn_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_conn_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_raid_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_raid_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_process_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_process_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_eventstore_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_ok_eventstore_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)

    # With node status = FAULT
    def test_fault_conn_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_conn_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_raid_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_raid_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_process_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_process_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_eventstore_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_fault_eventstore_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)


# ---------------------------------------------------------------------------
# TestUpdateImportNodeStatusOneNotUnknown (enhanced=False)
# ---------------------------------------------------------------------------

class TestUpdateImportNodeStatusOneNotUnknown:
    def test_conn_ok(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_conn_fault(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_ok(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_fault(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_process_ok(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_process_fault(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_eventstore_ok(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_eventstore_fault(self):
        _test_status(False, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)

    # With node status = OK
    def test_ok_conn_ok(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_ok_conn_fault(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_raid_ok(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_raid_fault(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_process_ok(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_process_fault(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_ok_eventstore_ok(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_ok_eventstore_fault(self):
        _test_status(False, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)

    # With node status = FAULT
    def test_fault_conn_ok(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_fault_conn_fault(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_raid_ok(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_raid_fault(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_process_ok(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_process_fault(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_fault_eventstore_ok(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_fault_eventstore_fault(self):
        _test_status(False, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)


# ---------------------------------------------------------------------------
# TestUpdateNodeStatusMultipleNotUnknownOkFirst
# ---------------------------------------------------------------------------

class TestUpdateNodeStatusMultipleNotUnknownOkFirst:
    # Connection = OK
    def test_conn_ok_raid_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_ok_raid_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_ok_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_conn_ok_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_conn_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_ok_proc_ok_es_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_raid_ok_proc_fault_es_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)

    # node=OK
    def test_n_ok_conn_ok_raid_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_ok_raid_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_ok_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_n_ok_conn_ok_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_n_ok_conn_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_ok_es_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_ok_es_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)

    # node=FAULT
    def test_n_fault_conn_ok_raid_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_ok_raid_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_ok_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_n_fault_conn_ok_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_OK)

    def test_n_fault_conn_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_ok_es_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_ok_es_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)


# ---------------------------------------------------------------------------
# TestUpdateNodeStatusMultipleNotUnknownFaultFirst
# ---------------------------------------------------------------------------

class TestUpdateNodeStatusMultipleNotUnknownFaultFirst:
    def test_conn_fault_raid_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_fault_raid_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_fault_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_fault_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_fault_proc_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_conn_fault_proc_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_fault_proc_ok(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_fault_proc_fault(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_fault_proc_ok_2(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_raid_fault_proc_fault_2(self):
        _test_status(True, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    # node=OK
    def test_n_ok_conn_fault_raid_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_fault_raid_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_fault_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_fault_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_fault_proc_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_conn_fault_proc_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_fault_proc_ok(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_fault_proc_fault(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_fault_proc_ok_2(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_ok_raid_fault_proc_fault_2(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    # node=FAULT
    def test_n_fault_conn_fault_raid_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_fault_raid_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_fault_raid_ok_proc_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_fault_raid_ok_proc_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_fault_proc_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_conn_fault_proc_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_fault_proc_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_fault_proc_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_fault_es_ok(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_OK, 0, NODE_STATUS_FAULT)

    def test_n_fault_raid_fault_es_fault(self):
        _test_status(True, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, NODE_STATUS_UNKNOWN, NODE_STATUS_FAULT, 0, NODE_STATUS_FAULT)


# ---------------------------------------------------------------------------
# TestUpdateNodeStatusPending
# ---------------------------------------------------------------------------

class TestUpdateNodeStatusPending:
    def test_eventstore_pending(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_PENDING, 0, NODE_STATUS_PENDING)

    def test_restart_needed(self):
        _test_status(True, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, 1, NODE_STATUS_RESTART)

    def test_fault_overrides_restart(self):
        _test_status(True, NODE_STATUS_PENDING, NODE_STATUS_FAULT, NODE_STATUS_OK, NODE_STATUS_OK, NODE_STATUS_OK, 1, NODE_STATUS_FAULT)


# ---------------------------------------------------------------------------
# TestIsProcessRunning
# ---------------------------------------------------------------------------

class TestIsProcessRunning:
    def test_empty_process_json(self):
        node = new_node("")
        assert node.is_process_running("so-test") is False

    def test_empty_json_object(self):
        node = new_node("")
        node.process_json = "{}"
        assert node.is_process_running("so-test") is False

    def test_different_process(self):
        node = new_node("")
        node.process_json = '{"containers":[{"Name":"so-foo", "Status":"running"}]}'
        assert node.is_process_running("so-test") is False

    def test_matching_running_process(self):
        node = new_node("")
        node.process_json = '{"containers":[{"Name":"so-test", "Status":"running"}]}'
        assert node.is_process_running("so-test") is True
