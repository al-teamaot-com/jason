from .datto_edr_av_api_contract import (
    ApiDiscoveryResult,
    ENDPOINT_SECURITY_DETECTION_READ,
    ENDPOINT_SECURITY_DETECTION_SEARCH,
    ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
    ENDPOINT_SECURITY_STATUS_READ,
    normalize_connector_detection,
    normalize_datto_alert,
    normalize_scan_verification,
    undocumented_keys,
)
from .datto_edr_av_security import EvidenceSource, ScanResultStatus


def test_normalizes_documented_datto_alert_fields_without_inference():
    item = normalize_datto_alert(
        {
            "id": "alert-1",
            "detectionId": "detect-1",
            "threatName": "Example",
            "threatSeverity": "high",
            "malicious": True,
            "compromised": False,
            "quarantined": True,
            "processName": "example.exe",
            "commandLine": "example.exe /x",
            "sha256": "abc",
            "originalPath": r"C:\\Temp\\example.exe",
        },
        evidence_ref="datto-api:alert-1",
    )
    assert item.alert_id == "alert-1"
    assert item.detection_id == "detect-1"
    assert item.malicious is True
    assert item.compromised is False
    assert item.quarantined is True
    assert item.execution_confirmed is None
    assert item.source == EvidenceSource.DATTO_EDR_API
    assert item.evidence_refs == ("datto-api:alert-1",)


def test_native_quarantine_is_accepted_as_provider_quarantine_evidence():
    item = normalize_datto_alert({"nativeQuarantine": True})
    assert item.quarantined is True


def test_unknown_fields_are_surfaced_for_connector_review():
    assert undocumented_keys({"deviceId": "D1", "futureDattoField": 1}) == (
        "futureDattoField",
    )


def test_api_preflight_fails_closed_when_threat_reads_are_missing():
    result = ApiDiscoveryResult(
        instance_url="https://example.infocyte.com",
        discovered_entities=("Alerts",),
        available_capabilities=(ENDPOINT_SECURITY_STATUS_READ,),
    )
    assert result.threat_branch_ready is False
    assert ENDPOINT_SECURITY_DETECTION_SEARCH in result.missing_for_threat()
    assert ENDPOINT_SECURITY_DETECTION_READ in result.missing_for_threat()
    assert ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH in result.missing_for_threat()


def test_api_preflight_can_prove_threat_read_surface_complete():
    result = ApiDiscoveryResult(
        instance_url="https://example.infocyte.com",
        discovered_entities=("Devices", "Alerts", "Scans"),
        available_capabilities=(
            ENDPOINT_SECURITY_STATUS_READ,
            ENDPOINT_SECURITY_DETECTION_SEARCH,
            ENDPOINT_SECURITY_DETECTION_READ,
            ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
        ),
    )
    assert result.threat_branch_ready is True
    assert result.missing_for_threat() == ()


def test_normalizes_governed_connector_provider_compromise_without_execution_inference():
    item = normalize_connector_detection(
        {
            "alert_id": "alert-50282",
            "detected": True,
            "severity": "high",
            "source_name": "EXP/CVE-2016-7228",
            "malicious": None,
            "quarantined": True,
            "provider_compromised": True,
            "threat_status": "Quarantined",
            "execution_status": "Unknown",
            "quarantine_records": [
                {
                    "detection_id": "detect-50282",
                    "status": "Quarantined",
                    "path": r"C:\\example.xls",
                }
            ],
        },
        evidence_ref="datto-edr:alert-50282",
    )
    assert item.alert_id == "alert-50282"
    assert item.detection_id == "detect-50282"
    assert item.detected is True
    assert item.quarantined is True
    assert item.malicious is None
    assert item.compromised is True
    assert item.threat_status == "Quarantined"
    assert item.execution_confirmed is None
    assert item.path.endswith("example.xls")


def test_completed_scan_without_post_scan_detection_check_is_not_clean():
    scan = normalize_scan_verification(
        {
            "id": "scan-1",
            "scan_type": "Quick scan",
            "status": "completed",
            "created_on": "2026-09-18T14:00:00Z",
        },
        post_scan_matching_detections=None,
        evidence_refs=("datto-scan:scan-1",),
    )
    assert scan.status == ScanResultStatus.UNKNOWN
    assert scan.result_read is True
    assert scan.post_scan_detection_check_clear is None
    assert scan.clean_for_completion is False


def test_completed_scan_plus_clear_post_scan_detection_check_is_clean():
    scan = normalize_scan_verification(
        {
            "id": "scan-2",
            "scan_type": "Quick scan",
            "status": "completed",
            "created_on": "2026-09-18T14:00:00Z",
        },
        post_scan_matching_detections=[],
        evidence_refs=("datto-scan:scan-2", "datto-alert-search:after-scan-2"),
    )
    assert scan.status == ScanResultStatus.CLEAN
    assert scan.unresolved_malicious_findings == 0
    assert scan.post_scan_detection_check_clear is True
    assert scan.clean_for_completion is True


def test_completed_scan_with_post_scan_matching_detection_has_findings():
    scan = normalize_scan_verification(
        {
            "id": "scan-3",
            "scan_type": "Quick scan",
            "status": "completed",
            "created_on": "2026-09-18T14:00:00Z",
        },
        post_scan_matching_detections=[{"alert_id": "new-alert"}],
    )
    assert scan.status == ScanResultStatus.FINDINGS_PRESENT
    assert scan.unresolved_malicious_findings == 1
    assert scan.post_scan_detection_check_clear is False
    assert scan.clean_for_completion is False
