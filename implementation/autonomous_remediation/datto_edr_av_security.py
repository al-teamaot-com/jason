"""Deterministic endpoint-security evidence model for the Datto EDR/AV playbook.

Datto EDR/AV product health and security-incident state are intentionally
separate. A healthy agent is not proof that a threat is resolved, and a
security alert is not proof that an endpoint is compromised.

This module contains no provider calls. Datto-specific API/webhook payloads are
normalized by a connector before the playbook consumes these observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class SecurityTrigger(str, Enum):
    HEALTH_ONLY = "health_only"
    THREAT_ONLY = "threat_only"
    HEALTH_AND_THREAT = "health_and_threat"

    @property
    def requires_threat_resolution(self) -> bool:
        return self in {self.THREAT_ONLY, self.HEALTH_AND_THREAT}


class EvidenceSource(str, Enum):
    DRMM_COMPONENT = "drmm_component"
    DATTO_EDR_API = "datto_edr_api"
    DATTO_WEBHOOK = "datto_webhook"
    DATTO_AV_SCAN = "datto_av_scan"
    AUTOTASK = "autotask"
    OTHER = "other"


class SecurityDisposition(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    NO_DETECTION = "no_detection"
    DETECTION_UNDER_INVESTIGATION = "detection_under_investigation"
    DETECTION_CONTAINED = "detection_contained"
    MALICIOUS_ARTIFACT_CONTAINED = "malicious_artifact_contained"
    FALSE_POSITIVE_REVIEW = "false_positive_review"
    RESOLVED = "resolved"
    SECURITY_INCIDENT_ESCALATION = "security_incident_escalation"


class CompromiseSignal(str, Enum):
    NOT_ESTABLISHED = "not_established"
    PROVIDER_INDICATED = "provider_indicated"
    CORROBORATED_EXECUTION = "corroborated_execution"


class ScanResultStatus(str, Enum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    CLEAN = "clean"
    FINDINGS_PRESENT = "findings_present"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ThreatObservation:
    """Normalized Datto security-detection evidence.

    The compromised field is retained as a provider-reported signal. It is not
    renamed to confirmed compromise by the playbook.
    """

    alert_id: str = ""
    detection_id: str = ""
    threat_name: str = ""
    severity: str = ""
    detected: bool | None = None
    malicious: bool | None = None
    not_malicious: bool | None = None
    suspicious: bool | None = None
    quarantined: bool | None = None
    blocked: bool | None = None
    resolved: bool | None = None
    compromised: bool | None = None
    execution_confirmed: bool | None = None
    detection_state: str = ""
    threat_status: str = ""
    process_name: str = ""
    parent_process_name: str = ""
    command_line: str = ""
    sha256: str = ""
    path: str = ""
    user: str = ""
    first_seen: str = ""
    last_seen: str = ""
    evidence_refs: tuple[str, ...] = ()
    source: EvidenceSource = EvidenceSource.DATTO_EDR_API


@dataclass(frozen=True)
class ScanObservation:
    scan_type: str
    status: ScanResultStatus
    unresolved_malicious_findings: int | None = None
    completed_at: str = ""
    result_read: bool = False
    provider_status: str = ""
    post_scan_detection_check_clear: bool | None = None
    evidence_refs: tuple[str, ...] = ()
    source: EvidenceSource = EvidenceSource.DATTO_AV_SCAN

    @property
    def clean_for_completion(self) -> bool:
        return (
            self.status == ScanResultStatus.CLEAN
            and self.result_read
            and self.unresolved_malicious_findings == 0
            and self.post_scan_detection_check_clear is True
        )


@dataclass(frozen=True)
class SecurityAssessment:
    disposition: SecurityDisposition
    compromise_signal: CompromiseSignal
    reason: str
    evidence_refs: tuple[str, ...] = ()
    source_set: tuple[EvidenceSource, ...] = ()

    @property
    def resolution_proven(self) -> bool:
        return self.disposition == SecurityDisposition.RESOLVED


def classify_security(
    threats: Sequence[ThreatObservation],
    *,
    scan: ScanObservation | None = None,
) -> SecurityAssessment:
    """Deterministically classify explicit provider/security evidence.

    This function deliberately does not infer compromise from product health,
    a single alert, a malicious file, or a failed scan.
    """

    items = tuple(threats)
    refs = _dedupe(ref for item in items for ref in item.evidence_refs)
    sources = _source_set(items, scan)

    if not items:
        return SecurityAssessment(
            disposition=SecurityDisposition.NO_DETECTION,
            compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
            reason="No relevant Datto security detection was supplied.",
            evidence_refs=refs,
            source_set=sources,
        )

    if all(item.not_malicious is True for item in items):
        return SecurityAssessment(
            disposition=SecurityDisposition.FALSE_POSITIVE_REVIEW,
            compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
            reason="All supplied detections are explicitly marked non-malicious by provider evidence.",
            evidence_refs=refs,
            source_set=sources,
        )

    relevant = tuple(item for item in items if item.not_malicious is not True)

    if any(item.execution_confirmed is True and item.malicious is True for item in relevant):
        return SecurityAssessment(
            disposition=SecurityDisposition.SECURITY_INCIDENT_ESCALATION,
            compromise_signal=CompromiseSignal.CORROBORATED_EXECUTION,
            reason="Malicious execution is explicitly corroborated; route to the security-incident path.",
            evidence_refs=refs,
            source_set=sources,
        )

    if any(item.compromised is True for item in relevant):
        return SecurityAssessment(
            disposition=SecurityDisposition.SECURITY_INCIDENT_ESCALATION,
            compromise_signal=CompromiseSignal.PROVIDER_INDICATED,
            reason="Datto provider evidence indicates compromised=true; escalate without relabeling the signal as independent proof.",
            evidence_refs=refs,
            source_set=sources,
        )

    malicious = tuple(item for item in relevant if item.malicious is True)
    if malicious:
        contained = all(
            item.quarantined is True or item.blocked is True or item.resolved is True
            for item in malicious
        )
        if contained and scan is not None and scan.clean_for_completion:
            scan_refs = _dedupe((*refs, *scan.evidence_refs))
            return SecurityAssessment(
                disposition=SecurityDisposition.RESOLVED,
                compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
                reason="Malicious artifacts are authoritatively contained/resolved and the verification scan is clean.",
                evidence_refs=scan_refs,
                source_set=sources,
            )
        if contained:
            return SecurityAssessment(
                disposition=SecurityDisposition.MALICIOUS_ARTIFACT_CONTAINED,
                compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
                reason="Malicious artifact evidence is contained, but final scan/recurrence verification is still required.",
                evidence_refs=refs,
                source_set=sources,
            )
        return SecurityAssessment(
            disposition=SecurityDisposition.DETECTION_UNDER_INVESTIGATION,
            compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
            reason="A malicious detection is present without authoritative containment/resolution evidence.",
            evidence_refs=refs,
            source_set=sources,
        )

    detected = tuple(
        item
        for item in relevant
        if item.detected is True or item.suspicious is True
    )
    if detected:
        contained = all(
            item.quarantined is True
            or item.blocked is True
            or item.resolved is True
            for item in detected
        )
        if contained and scan is not None and scan.clean_for_completion:
            scan_refs = _dedupe((*refs, *scan.evidence_refs))
            return SecurityAssessment(
                disposition=SecurityDisposition.RESOLVED,
                compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
                reason=(
                    "Provider detection evidence is contained and the "
                    "verification scan is clean; recurrence verification "
                    "remains a separate playbook completion gate."
                ),
                evidence_refs=scan_refs,
                source_set=sources,
            )
        if contained:
            return SecurityAssessment(
                disposition=SecurityDisposition.DETECTION_CONTAINED,
                compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
                reason=(
                    "Provider detection evidence is contained, but clean-scan "
                    "and recurrence verification are still required."
                ),
                evidence_refs=refs,
                source_set=sources,
            )

    if (
        scan is not None
        and scan.clean_for_completion
        and relevant
        and all(item.resolved is True for item in relevant)
    ):
        scan_refs = _dedupe((*refs, *scan.evidence_refs))
        return SecurityAssessment(
            disposition=SecurityDisposition.RESOLVED,
            compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
            reason="All relevant detections are provider-resolved and the verification scan is clean.",
            evidence_refs=scan_refs,
            source_set=sources,
        )

    return SecurityAssessment(
        disposition=SecurityDisposition.DETECTION_UNDER_INVESTIGATION,
        compromise_signal=CompromiseSignal.NOT_ESTABLISHED,
        reason="Detection evidence exists, but it does not establish compromise or final resolution.",
        evidence_refs=refs,
        source_set=sources,
    )


def _source_set(
    threats: Sequence[ThreatObservation],
    scan: ScanObservation | None,
) -> tuple[EvidenceSource, ...]:
    values = {item.source for item in threats}
    if scan is not None:
        values.add(scan.source)
    return tuple(sorted(values, key=lambda value: value.value))


def _dedupe(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


def find_exact_hash_recurrences(
    origin: ThreatObservation,
    candidates: Sequence[ThreatObservation],
) -> tuple[ThreatObservation, ...]:
    """Return later detections of the exact same artifact hash.

    Recurrence is intentionally conservative. Jason will not infer that two
    alerts are the same artifact from hostname, threat label, or filename
    alone. An exact SHA-256 is required, the alert must be distinct, and when
    both timestamps are present the candidate must be later than the origin.
    """
    origin_hash = str(origin.sha256 or "").strip().casefold()
    if not origin_hash:
        return ()
    matches = []
    for candidate in candidates:
        if candidate.alert_id and candidate.alert_id == origin.alert_id:
            continue
        if str(candidate.sha256 or "").strip().casefold() != origin_hash:
            continue
        if origin.first_seen and candidate.first_seen and candidate.first_seen <= origin.first_seen:
            continue
        matches.append(candidate)
    return tuple(matches)
