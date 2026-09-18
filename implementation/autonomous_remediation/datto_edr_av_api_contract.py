"""Datto EDR/AV API evidence contract for the governed playbook.

This module does not perform HTTP requests and does not contain credentials.
The Datto connector must discover the tenant's actual entities and operations
through the tenant LoopBack API Explorer, then expose normalized observations
to the playbook through governed Jason capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from datto_edr_av_security import (
    EvidenceSource,
    ScanObservation,
    ScanResultStatus,
    ThreatObservation,
)


# Provider-neutral Endpoint Security capability names. These are registered
# through Jason governance and backed by the read-only Datto EDR connector.
ENDPOINT_SECURITY_STATUS_READ = "endpoint.security.status.read"
ENDPOINT_SECURITY_DETECTION_SEARCH = "endpoint.security.detection.search"
ENDPOINT_SECURITY_DETECTION_READ = "endpoint.security.detection.read"
ENDPOINT_SECURITY_POLICY_READ = "endpoint.security.policy.read"
ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH = "endpoint.security.scan.history.search"
ENDPOINT_SECURITY_QUARANTINE_SEARCH = "endpoint.security.quarantine.search"
ENDPOINT_SECURITY_SCAN_EXECUTE = "endpoint.security.scan.execute"


READ_CAPABILITIES = (
    ENDPOINT_SECURITY_STATUS_READ,
    ENDPOINT_SECURITY_DETECTION_SEARCH,
    ENDPOINT_SECURITY_DETECTION_READ,
    ENDPOINT_SECURITY_POLICY_READ,
    ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
    ENDPOINT_SECURITY_QUARANTINE_SEARCH,
)

THREAT_BRANCH_REQUIRED_READS = (
    ENDPOINT_SECURITY_STATUS_READ,
    ENDPOINT_SECURITY_DETECTION_SEARCH,
    ENDPOINT_SECURITY_DETECTION_READ,
    ENDPOINT_SECURITY_SCAN_HISTORY_SEARCH,
)

HEALTH_BRANCH_REQUIRED_READS = (
    ENDPOINT_SECURITY_STATUS_READ,
    ENDPOINT_SECURITY_POLICY_READ,
)


# Fields are taken from Datto's documented webhook/alert metadata vocabulary.
DOCUMENTED_ALERT_FIELDS = frozenset(
    {
        "agentId",
        "deviceId",
        "engineVersion",
        "vdfVersion",
        "malicious",
        "notMalicious",
        "suspicious",
        "compromised",
        "quarantined",
        "nativeQuarantine",
        "blocked",
        "threatName",
        "avThreatName",
        "threatSeverity",
        "threatStatus",
        "detectionId",
        "detectionName",
        "detectionState",
        "detectionTime",
        "eventTime",
        "processName",
        "parentProcessName",
        "commandLine",
        "sha256",
        "path",
        "originalPath",
        "detectionUser",
        "hostname",
        "organizationId",
        "organizationName",
        "locationId",
        "rmmDeviceId",
        "rmmSiteId",
        "isolated",
    }
)


@dataclass(frozen=True)
class ApiDiscoveryResult:
    instance_url: str
    discovered_entities: tuple[str, ...]
    available_capabilities: tuple[str, ...]
    evidence_ref: str = ""

    def missing_for_health(self) -> tuple[str, ...]:
        return _missing(self.available_capabilities, HEALTH_BRANCH_REQUIRED_READS)

    def missing_for_threat(self) -> tuple[str, ...]:
        return _missing(self.available_capabilities, THREAT_BRANCH_REQUIRED_READS)

    @property
    def health_branch_ready(self) -> bool:
        return not self.missing_for_health()

    @property
    def threat_branch_ready(self) -> bool:
        return not self.missing_for_threat()


def normalize_datto_alert(
    payload: Mapping[str, Any],
    *,
    evidence_ref: str = "",
) -> ThreatObservation:
    """Normalize documented Datto alert/webhook metadata without over-interpreting it."""

    return ThreatObservation(
        alert_id=_first_text(payload, "id", "threatId"),
        detection_id=_first_text(payload, "detectionId"),
        threat_name=_first_text(payload, "threatName", "avThreatName", "detectionName"),
        severity=_first_text(payload, "threatSeverity", "ruleSeverity", "severity"),
        detected=True,
        malicious=_optional_bool(payload.get("malicious")),
        not_malicious=_optional_bool(payload.get("notMalicious")),
        suspicious=_optional_bool(payload.get("suspicious")),
        quarantined=_first_bool(payload, "quarantined", "nativeQuarantine"),
        blocked=_optional_bool(payload.get("blocked")),
        # Datto exposes this as provider metadata. The security model preserves
        # it as a provider-indicated compromise signal, not independent proof.
        compromised=_optional_bool(payload.get("compromised")),
        # Never derive execution confirmation from a free-form status string.
        # A connector may set this later only from explicit corroborating evidence.
        execution_confirmed=None,
        detection_state=_first_text(payload, "detectionState"),
        threat_status=_first_text(payload, "threatStatus"),
        process_name=_first_text(payload, "processName"),
        parent_process_name=_first_text(payload, "parentProcessName"),
        command_line=_first_text(payload, "commandLine"),
        sha256=_first_text(payload, "sha256"),
        path=_first_text(payload, "originalPath", "path"),
        user=_first_text(payload, "detectionUser"),
        first_seen=_first_text(payload, "detectionTime", "eventTime"),
        last_seen=_first_text(payload, "eventTime", "detectionTime"),
        evidence_refs=(evidence_ref,) if evidence_ref else (),
        source=EvidenceSource.DATTO_EDR_API,
    )


def normalize_connector_detection(
    payload: Mapping[str, Any],
    *,
    evidence_ref: str = "",
) -> ThreatObservation:
    """Normalize Jason's governed Datto EDR detection-read result."""

    quarantine = payload.get("quarantine_records")
    first_quarantine = (
        quarantine[0]
        if isinstance(quarantine, list)
        and quarantine
        and isinstance(quarantine[0], Mapping)
        else {}
    )
    return ThreatObservation(
        alert_id=_first_text(payload, "alert_id", "id"),
        detection_id=_first_text(payload, "detection_id")
        or _first_text(first_quarantine, "detection_id"),
        threat_name=_first_text(
            payload,
            "threat_name",
            "source_name",
            "name",
        ),
        severity=_first_text(payload, "severity"),
        detected=_optional_bool(payload.get("detected")),
        malicious=_optional_bool(payload.get("malicious")),
        not_malicious=_optional_bool(payload.get("not_malicious")),
        suspicious=_optional_bool(payload.get("suspicious")),
        quarantined=_optional_bool(payload.get("quarantined")),
        blocked=_optional_bool(payload.get("blocked")),
        resolved=_optional_bool(payload.get("resolved")),
        compromised=_optional_bool(
            payload.get("provider_compromised")
            if "provider_compromised" in payload
            else payload.get("compromised")
        ),
        execution_confirmed=None,
        threat_status=_first_text(payload, "threat_status"),
        detection_state=_first_text(payload, "detection_state"),
        sha256=_first_text(payload, "sha256"),
        path=_first_text(payload, "path")
        or _first_text(first_quarantine, "path"),
        first_seen=_first_text(payload, "event_time", "created_on"),
        last_seen=_first_text(payload, "created_on", "event_time"),
        evidence_refs=(evidence_ref,) if evidence_ref else (),
        source=EvidenceSource.DATTO_EDR_API,
    )


def normalize_scan_verification(
    scan_payload: Mapping[str, Any],
    *,
    post_scan_matching_detections: Sequence[Mapping[str, Any]] | None,
    evidence_refs: Sequence[str] = (),
) -> ScanObservation:
    """Build composite Datto AV scan-verification evidence.

    Datto's ScanHistoryTracking record proves scan execution/status but does
    not expose a "zero threats found" result. Therefore a completed scan is
    classified CLEAN only when a separate post-scan detection query has also
    completed and returned no unresolved/matching detections.
    """

    provider_status = _first_text(scan_payload, "status").casefold()
    scan_type = _first_text(scan_payload, "scan_type", "scanType")
    completed_at = _first_text(
        scan_payload,
        "completed_at",
        "completedOn",
        "created_on",
        "createdOn",
    )

    if provider_status in {"failed", "error", "cancelled", "canceled"}:
        status = ScanResultStatus.FAILED
        unresolved = None
        post_scan_clear = None
    elif provider_status in {"running", "queued", "pending", "in progress"}:
        status = ScanResultStatus.RUNNING
        unresolved = None
        post_scan_clear = None
    elif provider_status == "completed":
        if post_scan_matching_detections is None:
            status = ScanResultStatus.UNKNOWN
            unresolved = None
            post_scan_clear = None
        else:
            unresolved = len(tuple(post_scan_matching_detections))
            post_scan_clear = unresolved == 0
            status = (
                ScanResultStatus.CLEAN
                if post_scan_clear
                else ScanResultStatus.FINDINGS_PRESENT
            )
    else:
        status = ScanResultStatus.UNKNOWN
        unresolved = None
        post_scan_clear = None

    return ScanObservation(
        scan_type=scan_type,
        status=status,
        unresolved_malicious_findings=unresolved,
        completed_at=completed_at,
        result_read=True,
        provider_status=provider_status,
        post_scan_detection_check_clear=post_scan_clear,
        evidence_refs=tuple(str(ref) for ref in evidence_refs if str(ref)),
        source=EvidenceSource.DATTO_AV_SCAN,
    )


def undocumented_keys(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Surface new/unknown provider fields for review rather than silently relying on them."""

    ignored_envelope = {"id", "threatId", "ruleSeverity"}
    return tuple(
        sorted(
            key
            for key in payload
            if key not in DOCUMENTED_ALERT_FIELDS and key not in ignored_envelope
        )
    )


def _missing(
    available: Sequence[str],
    required: Sequence[str],
) -> tuple[str, ...]:
    current = set(available)
    return tuple(item for item in required if item not in current)


def _first_text(payload: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_bool(payload: Mapping[str, Any], *keys: str) -> bool | None:
    seen_false = False
    for key in keys:
        value = _optional_bool(payload.get(key))
        if value is True:
            return True
        if value is False:
            seen_false = True
    return False if seen_false else None


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None
