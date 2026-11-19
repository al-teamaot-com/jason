"""Read-only Windows shutdown evidence classification using existing source helpers.

This is an isolated *classification* adapter. It neither verifies ticket
ownership nor executes alert/ticket modifications; those remain separately
governed and unimplemented in the JSON runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .unexpected_shutdown_analysis import (
    INCIDENT_WINDOW_MS, classify_site_scope, protected_role,
    shutdown_character, site_event_id, storage_health_risk,
)


class ShutdownJsonBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ShutdownJsonAssessment:
    disposition: str
    shutdown_character: str
    site_scope: str
    site_incident_id: str | None
    storage_risk: bool
    risk_reasons: tuple[str, ...]
    affected_physical_devices: int
    excluded_vm_count: int
    live_mutations: int = 0


def classify_shutdown_json_readonly(
    *,
    exact_client_id: str,
    target_uid: str,
    target_site_uid: str,
    endpoint: Mapping[str, Any],
    incident_timestamp_ms: int,
    peer_shutdowns: Sequence[Mapping[str, Any]],
    windows_events: Sequence[Mapping[str, Any]],
    whea_events: Sequence[Mapping[str, Any]],
    physical_disks: Sequence[Mapping[str, Any]],
    reliability: Sequence[Mapping[str, Any]],
    volumes: Sequence[Mapping[str, Any]],
    independent_recurring_incidents: int,
    health_evidence_complete: bool,
) -> ShutdownJsonAssessment:
    if not exact_client_id or not target_uid or not target_site_uid:
        raise ShutdownJsonBoundaryError("SHUTDOWN_EXACT_SCOPE_REQUIRED")
    if (str(endpoint.get("resource_id") or "") != target_uid or
        str(endpoint.get("companyID") or "") != exact_client_id or
        str(endpoint.get("site_uid") or endpoint.get("siteUid") or endpoint.get("site_id") or "")
        != target_site_uid):
        raise ShutdownJsonBoundaryError("SHUTDOWN_ENDPOINT_SCOPE_MISMATCH")
    if not isinstance(incident_timestamp_ms, int) or incident_timestamp_ms <= 0:
        raise ShutdownJsonBoundaryError("SHUTDOWN_INCIDENT_TIME_UNVERIFIED")
    if not isinstance(independent_recurring_incidents, int) or independent_recurring_incidents < 0:
        raise ShutdownJsonBoundaryError("SHUTDOWN_RECURRENCE_UNVERIFIED")
    if not health_evidence_complete:
        raise ShutdownJsonBoundaryError("SHUTDOWN_HEALTH_EVIDENCE_INCOMPLETE")
    if not isinstance(peer_shutdowns, Sequence) or len(peer_shutdowns) > 100:
        raise ShutdownJsonBoundaryError("SHUTDOWN_PEERS_UNBOUNDED")
    if endpoint.get("is_virtual") is not False:
        raise ShutdownJsonBoundaryError("SHUTDOWN_TARGET_PHYSICAL_SCOPE_UNVERIFIED")
    affected = {target_uid}
    excluded_vm = 0
    ambiguous = 0
    anchor = incident_timestamp_ms
    for item in peer_shutdowns:
        if not isinstance(item, Mapping):
            raise ShutdownJsonBoundaryError("SHUTDOWN_PEER_NOT_AUTHORITATIVE")
        if (str(item.get("companyID") or "") != exact_client_id or
            str(item.get("site_uid") or "") != target_site_uid):
            raise ShutdownJsonBoundaryError("SHUTDOWN_CROSS_CLIENT_SITE_PEER")
        uid = str(item.get("resource_id") or "")
        if not uid:
            raise ShutdownJsonBoundaryError("SHUTDOWN_PEER_UID_MISSING")
        timestamp = item.get("incident_timestamp_ms")
        if not isinstance(timestamp, int) or timestamp <= 0:
            raise ShutdownJsonBoundaryError("SHUTDOWN_PEER_TIME_UNVERIFIED")
        if abs(timestamp - incident_timestamp_ms) > INCIDENT_WINDOW_MS:
            continue
        virtual = item.get("is_virtual")
        if virtual is True:
            excluded_vm += 1
            continue
        if virtual is not False:
            ambiguous += 1
            continue
        affected.add(uid)
        anchor = min(anchor, timestamp)
    site_scope = classify_site_scope(
        affected_physical_devices=len(affected),
        active_physical_devices=max(len(affected), 1),
        ambiguous_physical_devices=ambiguous,
    )
    character = shutdown_character(windows_events)
    risk, reasons = storage_health_risk(
        events=windows_events, whea_events=whea_events,
        physical_disks=physical_disks, reliability=reliability, volumes=volumes,
    )
    event_id = site_event_id(target_site_uid, anchor) if len(affected) > 1 else None
    if endpoint.get("online") is not True:
        disposition = "waiting_device_access"
    elif protected_role(endpoint):
        disposition = "protected_role_review"
    elif risk:
        disposition = "device_specific_risk"
    elif independent_recurring_incidents >= 2:
        disposition = "recurring_issue"
    elif character == "UNDETERMINED":
        disposition = "evidence_inconclusive"
    elif ambiguous:
        disposition = "evidence_inconclusive"
    elif site_scope == "SITE_ENVIRONMENTAL":
        disposition = "site_environmental_classified"
    elif site_scope == "SITE_CORRELATED_SMALL_SITE":
        disposition = "site_correlated_small_site_review"
    else:
        disposition = "device_specific_review"
    return ShutdownJsonAssessment(
        disposition=disposition, shutdown_character=character,
        site_scope=site_scope, site_incident_id=event_id,
        storage_risk=risk, risk_reasons=reasons,
        affected_physical_devices=len(affected),
        excluded_vm_count=excluded_vm,
    )
