import pytest

from connectors.datto_edr.threat_correlation import (
    AmbiguousThreatCorrelationError,
    ThreatCorrelationError,
    correlate_drmm_threat_to_edr_detection,
)


DEVICE_UID = "69571572-83f7-1e33-9cdf-01717d4e74a4"
AGENT_ID = "0cf9b495-879b-4b6c-8c60-ac229e01d136"


def drmm_alert():
    return {
        "alertUid": "bd0882e0-8700-4985-ad89-f789b865c76e",
        "timestamp": 1789720844000,
        "alertContext": {
            "@class": "endpoint_security_threat_ctx",
            "esAlertId": "15884344",
            "description": "Detected threat from Datto AV",
        },
        "alertSourceInfo": {"deviceUid": DEVICE_UID, "deviceName": "AOT-50282"},
    }


def edr_detection(alert_id="c3aa92e3-92af-4c8f-889a-51bafa50790f"):
    return {
        "alert_id": alert_id,
        "agent_id": AGENT_ID,
        "device_id": DEVICE_UID,
        "source_type": "av",
        "signal": True,
        "event_time": "2026-09-18T08:40:41.000Z",
        "created_on": "2026-09-18T08:40:44.569Z",
    }


def test_correlates_live_aot_50282_pattern_without_hostname_selection():
    result = correlate_drmm_threat_to_edr_detection(
        threat_reference="15884344",
        drmm_alert=drmm_alert(),
        edr_detections=[edr_detection()],
        device_uid=DEVICE_UID,
        agent_id=AGENT_ID,
    )
    assert result.edr_alert_id == "c3aa92e3-92af-4c8f-889a-51bafa50790f"
    assert result.drmm_alert_uid == "bd0882e0-8700-4985-ad89-f789b865c76e"
    assert result.event_delta_seconds <= 5
    assert "exact_device_uid" in result.basis


def test_wrong_drmm_threat_reference_fails_closed():
    with pytest.raises(ThreatCorrelationError, match="threat reference"):
        correlate_drmm_threat_to_edr_detection(
            threat_reference="wrong",
            drmm_alert=drmm_alert(),
            edr_detections=[edr_detection()],
            device_uid=DEVICE_UID,
            agent_id=AGENT_ID,
        )


def test_duplicate_plausible_edr_events_are_ambiguous():
    with pytest.raises(AmbiguousThreatCorrelationError):
        correlate_drmm_threat_to_edr_detection(
            threat_reference="15884344",
            drmm_alert=drmm_alert(),
            edr_detections=[edr_detection("one"), edr_detection("two")],
            device_uid=DEVICE_UID,
            agent_id=AGENT_ID,
        )


def test_hostname_match_cannot_override_wrong_durable_device_identity():
    wrong = edr_detection()
    wrong["device_id"] = "different-device"
    wrong["hostname"] = "AOT-50282"
    with pytest.raises(ThreatCorrelationError, match="no Datto EDR"):
        correlate_drmm_threat_to_edr_detection(
            threat_reference="15884344",
            drmm_alert=drmm_alert(),
            edr_detections=[wrong],
            device_uid=DEVICE_UID,
            agent_id=AGENT_ID,
        )
