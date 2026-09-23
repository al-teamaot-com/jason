from .datto_edr_av_playbook import (
    HealthObservation,
    PlaybookRun,
    PlaybookState,
    metrics_payload,
    next_action,
)
from .datto_edr_av_security import (
    CompromiseSignal,
    ScanObservation,
    ScanResultStatus,
    SecurityDisposition,
    SecurityTrigger,
    ThreatObservation,
)


def run(trigger: SecurityTrigger) -> PlaybookRun:
    return PlaybookRun(
        run_id="run-security",
        ticket_id="T20260918.0005",
        device_id="AOT-50282",
        organization_id="AOT",
        client_id="AOT",
        security_trigger=trigger,
    )


def clean_scan() -> ScanObservation:
    return ScanObservation(
        scan_type="quick",
        status=ScanResultStatus.CLEAN,
        unresolved_malicious_findings=0,
        completed_at="2026-09-18T12:00:00Z",
        result_read=True,
        provider_status="completed",
        post_scan_detection_check_clear=True,
        evidence_refs=("scan:clean",),
    )


def test_threat_trigger_cannot_close_on_stack_health_alone():
    r = run(SecurityTrigger.THREAT_ONLY)
    action = next_action(r, HealthObservation(status="Healthy"))
    assert action is None
    assert r.state == PlaybookState.AWAITING_SECURITY_VERIFICATION
    assert r.completion_ready is False


def test_health_only_ticket_keeps_existing_healthy_terminal_behavior():
    r = run(SecurityTrigger.HEALTH_ONLY)
    action = next_action(r, HealthObservation(status="Healthy"))
    assert action is None
    assert r.state == PlaybookState.HEALTHY
    assert r.completion_ready is True


def test_quarantined_malware_is_contained_not_compromise():
    r = run(SecurityTrigger.HEALTH_AND_THREAT)
    r.record_health(HealthObservation(status="Healthy"))
    assessment = r.record_security_evidence(
        [
            ThreatObservation(
                alert_id="alert-1",
                malicious=True,
                quarantined=True,
                evidence_refs=("datto-alert:alert-1",),
            )
        ]
    )
    assert assessment.disposition == SecurityDisposition.MALICIOUS_ARTIFACT_CONTAINED
    assert assessment.compromise_signal == CompromiseSignal.NOT_ESTABLISHED
    assert r.state == PlaybookState.THREAT_CONTAINED
    assert r.completion_ready is False


def test_clean_scan_still_requires_recurrence_check_before_completion():
    r = run(SecurityTrigger.HEALTH_AND_THREAT)
    r.record_health(HealthObservation(status="Healthy"))
    r.record_security_evidence(
        [ThreatObservation(alert_id="alert-2", malicious=True, quarantined=True)]
    )
    r.record_scan(clean_scan())
    assert r.last_security is not None
    assert r.last_security.disposition == SecurityDisposition.RESOLVED
    assert r.state == PlaybookState.AWAITING_SECURITY_VERIFICATION
    assert r.completion_ready is False

    r.record_recurrence_check(clear=True, evidence_refs=("recurrence:clear",))
    assert r.state == PlaybookState.HEALTHY
    assert r.recurrence_verified is True
    assert r.completion_ready is True


def test_provider_compromised_signal_escalates_without_health_conflation():
    r = run(SecurityTrigger.THREAT_ONLY)
    r.record_health(HealthObservation(status="Healthy"))
    assessment = r.record_security_evidence(
        [ThreatObservation(alert_id="alert-3", malicious=True, compromised=True)]
    )
    assert assessment.compromise_signal == CompromiseSignal.PROVIDER_INDICATED
    assert r.state == PlaybookState.ESCALATION_REQUIRED


def test_metrics_expose_independent_health_and_security_states():
    r = run(SecurityTrigger.THREAT_ONLY)
    r.record_health(HealthObservation(status="Healthy"))
    r.record_security_evidence(
        [ThreatObservation(alert_id="alert-4", malicious=True, quarantined=True)]
    )
    metrics = metrics_payload(r)
    assert metrics["security_stack_healthy"] is True
    assert metrics["threat_resolution_required"] is True
    assert metrics["threat_resolved"] is False
    assert metrics["security_disposition"] == "malicious_artifact_contained"
    assert metrics["compromise_signal"] == "not_established"
    assert "datto_edr_api" in metrics["evidence_sources"]


def test_telemetry_event_is_low_cardinality_and_aggregate_safe():
    from .datto_edr_av_playbook import telemetry_event

    r = run(SecurityTrigger.THREAT_ONLY)
    r.record_health(HealthObservation(status="Healthy"))
    r.record_security_evidence(
        [ThreatObservation(alert_id="secret-alert-id", suspicious=True)]
    )
    event = telemetry_event(
        r,
        timestamp="2026-09-18T12:00:00Z",
        outcome="investigating",
        duration_seconds=42,
        verification_passed=False,
        steps=({"name": "health_check", "result": "pass"},),
    )
    assert event["playbook_id"] == "datto_edr_av"
    assert event["classification"] == "threat_only"
    assert event["security_disposition"] == "detection_under_investigation"
    assert "ticket_id" not in event
    assert "device_id" not in event
    assert "secret-alert-id" not in str(event)


def test_datto_av_detection_quarantined_without_malicious_flag_is_contained_not_compromised():
    r = run(SecurityTrigger.THREAT_ONLY)
    r.record_health(HealthObservation(status="Healthy"))
    assessment = r.record_security_evidence(
        [
            ThreatObservation(
                alert_id="aot-50282-current",
                detected=True,
                malicious=None,
                compromised=None,
                quarantined=True,
                threat_name="EXP/CVE-2016-7228",
                evidence_refs=("datto-alert:aot-50282-current",),
            )
        ]
    )
    assert assessment.disposition == SecurityDisposition.DETECTION_CONTAINED
    assert assessment.compromise_signal == CompromiseSignal.NOT_ESTABLISHED
    assert r.state == PlaybookState.THREAT_CONTAINED
    assert r.completion_ready is False


def test_recurrence_failure_reopens_investigation_state():
    r = run(SecurityTrigger.THREAT_ONLY)
    r.record_health(HealthObservation(status="Healthy"))
    r.record_security_evidence(
        [ThreatObservation(alert_id="alert-5", detected=True, quarantined=True)]
    )
    r.record_scan(clean_scan())
    assert r.state == PlaybookState.AWAITING_SECURITY_VERIFICATION

    r.record_recurrence_check(clear=False, evidence_refs=("recurrence:new-alert",))
    assert r.recurrence_verified is False
    assert r.state == PlaybookState.THREAT_INVESTIGATION
    assert r.completion_ready is False
