from datto_edr_av_security import (
    CompromiseSignal,
    EvidenceSource,
    ScanObservation,
    ScanResultStatus,
    SecurityDisposition,
    ThreatObservation,
    classify_security,
)


def clean_scan() -> ScanObservation:
    return ScanObservation(
        scan_type="quick",
        status=ScanResultStatus.CLEAN,
        unresolved_malicious_findings=0,
        result_read=True,
        provider_status="completed",
        post_scan_detection_check_clear=True,
        evidence_refs=("scan:1",),
    )


def test_alert_is_not_compromise_by_default():
    result = classify_security(
        [ThreatObservation(alert_id="A1", suspicious=True, evidence_refs=("alert:A1",))]
    )
    assert result.disposition == SecurityDisposition.DETECTION_UNDER_INVESTIGATION
    assert result.compromise_signal == CompromiseSignal.NOT_ESTABLISHED


def test_quarantined_malicious_artifact_does_not_establish_compromise():
    result = classify_security(
        [
            ThreatObservation(
                alert_id="A2",
                malicious=True,
                quarantined=True,
                evidence_refs=("alert:A2",),
            )
        ]
    )
    assert result.disposition == SecurityDisposition.MALICIOUS_ARTIFACT_CONTAINED
    assert result.compromise_signal == CompromiseSignal.NOT_ESTABLISHED


def test_contained_artifact_plus_clean_read_scan_can_resolve():
    result = classify_security(
        [ThreatObservation(alert_id="A3", malicious=True, quarantined=True)],
        scan=clean_scan(),
    )
    assert result.disposition == SecurityDisposition.RESOLVED
    assert result.resolution_proven is True


def test_provider_compromised_flag_is_preserved_as_provider_signal():
    result = classify_security(
        [ThreatObservation(alert_id="A4", compromised=True, malicious=True)]
    )
    assert result.disposition == SecurityDisposition.SECURITY_INCIDENT_ESCALATION
    assert result.compromise_signal == CompromiseSignal.PROVIDER_INDICATED


def test_corroborated_malicious_execution_escalates():
    result = classify_security(
        [
            ThreatObservation(
                alert_id="A5",
                malicious=True,
                execution_confirmed=True,
            )
        ]
    )
    assert result.disposition == SecurityDisposition.SECURITY_INCIDENT_ESCALATION
    assert result.compromise_signal == CompromiseSignal.CORROBORATED_EXECUTION


def test_explicit_non_malicious_detections_route_to_false_positive_review():
    result = classify_security(
        [ThreatObservation(alert_id="A6", not_malicious=True)]
    )
    assert result.disposition == SecurityDisposition.FALSE_POSITIVE_REVIEW
    assert result.compromise_signal == CompromiseSignal.NOT_ESTABLISHED


def test_failed_scan_never_proves_resolution():
    scan = ScanObservation(
        scan_type="quick",
        status=ScanResultStatus.FAILED,
        unresolved_malicious_findings=None,
        result_read=True,
    )
    result = classify_security(
        [ThreatObservation(alert_id="A7", malicious=True, quarantined=True)],
        scan=scan,
    )
    assert result.disposition == SecurityDisposition.MALICIOUS_ARTIFACT_CONTAINED


def test_sources_are_preserved_for_telemetry():
    result = classify_security(
        [
            ThreatObservation(
                alert_id="A8",
                suspicious=True,
                source=EvidenceSource.DATTO_WEBHOOK,
            )
        ],
        scan=clean_scan(),
    )
    assert EvidenceSource.DATTO_WEBHOOK in result.source_set
    assert EvidenceSource.DATTO_AV_SCAN in result.source_set


def test_detected_quarantined_item_without_malicious_flag_is_detection_contained():
    result = classify_security(
        [
            ThreatObservation(
                alert_id="A9",
                detected=True,
                quarantined=True,
                malicious=None,
                compromised=None,
            )
        ]
    )
    assert result.disposition == SecurityDisposition.DETECTION_CONTAINED
    assert result.compromise_signal == CompromiseSignal.NOT_ESTABLISHED


def test_detected_contained_item_plus_clean_scan_can_resolve_security_assessment():
    result = classify_security(
        [
            ThreatObservation(
                alert_id="A10",
                detected=True,
                quarantined=True,
                malicious=None,
            )
        ],
        scan=clean_scan(),
    )
    assert result.disposition == SecurityDisposition.RESOLVED
    assert result.compromise_signal == CompromiseSignal.NOT_ESTABLISHED


def test_recurrence_requires_exact_sha256_and_later_distinct_alert():
    from datto_edr_av_security import find_exact_hash_recurrences
    origin = ThreatObservation(alert_id="a1", sha256="ABC", first_seen="2026-09-11T08:27:32Z")
    candidates = [
        ThreatObservation(alert_id="a1", sha256="ABC", first_seen="2026-09-11T08:27:32Z"),
        ThreatObservation(alert_id="a2", sha256="abc", first_seen="2026-09-18T08:40:41Z"),
        ThreatObservation(alert_id="a3", sha256="different", first_seen="2026-09-18T08:40:41Z"),
    ]
    matches = find_exact_hash_recurrences(origin, candidates)
    assert [item.alert_id for item in matches] == ["a2"]


def test_recurrence_fails_closed_without_artifact_hash():
    from datto_edr_av_security import find_exact_hash_recurrences
    origin = ThreatObservation(alert_id="a1", threat_name="same", sha256="")
    candidate = ThreatObservation(alert_id="a2", threat_name="same", sha256="")
    assert find_exact_hash_recurrences(origin, [candidate]) == ()
