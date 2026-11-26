"""Deterministic source-matched, read-only POST and Event ID 7 triage.

The legacy deployed worker currently performs a conservative diagnostic and
human handoff, not the broader authored auto-close path. This code deliberately
preserves that installed conservative behavior and no hardware modification.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping, Sequence


class JsonHardwareTriageError(RuntimeError):
    pass


@dataclass(frozen=True)
class HardwareTriageAssessment:
    playbook: str
    disposition: str
    event_count: int
    protected_role: bool
    recurring: bool
    source_alert_uid: str | None
    disk_number: str | None
    removable_hint_count: int
    autonomous_alert_resolution_allowed: bool = False
    autonomous_hardware_mutation_allowed: bool = False


def classify_hardware_triage(
    *,
    playbook: str,
    client_id: str,
    device_uid: str,
    device_hostname: str,
    ticket_number: str,
    endpoint: Mapping[str, Any],
    alerts: Sequence[Mapping[str, Any]],
    audit: Mapping[str, Any] | None = None,
) -> HardwareTriageAssessment:
    if playbook not in {"disk_bad_block_event_7", "post_error_investigation"}:
        raise JsonHardwareTriageError("HARDWARE_SOURCE_NOT_ALLOWED")
    if (not client_id or not device_uid or not device_hostname or
        str(endpoint.get("resource_id") or "") != device_uid or
        str(endpoint.get("companyID") or "") != client_id or
        str(endpoint.get("hostname") or "").casefold() != device_hostname.casefold()):
        raise JsonHardwareTriageError("HARDWARE_CROSS_SCOPE_OR_DEVICE_CHANGED")
    if endpoint.get("online") is not True:
        return HardwareTriageAssessment(
            playbook, "waiting_device_access", 0, False, False,
            None, None, 0)
    if not isinstance(alerts, Sequence) or len(alerts) > 1000:
        raise JsonHardwareTriageError("HARDWARE_ALERT_HISTORY_UNBOUNDED")
    valid = []
    unique_tickets = set()
    for alert in alerts:
        if not isinstance(alert, Mapping):
            raise JsonHardwareTriageError("HARDWARE_ALERT_HISTORY_INVALID")
        info = alert.get("alertSourceInfo")
        if isinstance(info, Mapping) and str(info.get("deviceUid") or "") != device_uid:
            raise JsonHardwareTriageError("HARDWARE_ALERT_DEVICE_UID_MISMATCH")
        context = alert.get("alertContext")
        context_map = context if isinstance(context, Mapping) else {}
        material = json.dumps(alert,sort_keys=True,default=str).casefold()
        if playbook == "disk_bad_block_event_7":
            matched = (str(context_map.get("code") or "") == "7"
                       or "bad block" in material)
        else:
            matched = ("power-on-self-test" in material or
                       "post errors occurred" in material)
        if matched:
            valid.append(alert)
            number = str(alert.get("ticketNumber") or "").strip()
            if number:
                unique_tickets.add(number)
    if not valid:
        return HardwareTriageAssessment(
            playbook, "no_authoritative_matching_alert_human_review",
            0, False, False, None, None, 0)
    exact = next((item for item in valid if item.get("ticketNumber") == ticket_number),None)
    if exact is None:
        exact = max(valid,key=lambda item:int(item.get("timestamp") or 0))
    uid = str(exact.get("alertUid") or "").strip()
    if not uid:
        raise JsonHardwareTriageError("HARDWARE_ALERT_UID_MISSING")
    recurring = len(valid) >= 2 or len(unique_tickets) >= 2
    role = json.dumps({
        "device_type":endpoint.get("device_type"),
        "operating_system":endpoint.get("operating_system") or endpoint.get("operatingSystem"),
    },sort_keys=True,default=str).casefold()
    protected = any(token in role for token in (
        "server","domain controller","hyper-v","hyperv","physical host"))
    if playbook == "post_error_investigation":
        disposition = (
            "protected_role_human_review" if protected else
            "recurring_post_human_review" if recurring else
            "isolated_post_diagnostic_only_human_review"
        )
        return HardwareTriageAssessment(
            playbook,disposition,len(valid),protected,recurring,uid,None,0)
    if not isinstance(audit, Mapping):
        raise JsonHardwareTriageError("HARDWARE_DISK_AUDIT_MISSING")
    attached=audit.get("attachedDevices")
    logical=audit.get("logicalDisks")
    if attached is None and isinstance(audit.get("audit"),Mapping):
        attached=audit["audit"].get("attachedDevices")
        logical=audit["audit"].get("logicalDisks")
    if not isinstance(attached,list) or not isinstance(logical,list):
        raise JsonHardwareTriageError("HARDWARE_DISK_AUDIT_INCOMPLETE")
    hints=sum(
        any(token in json.dumps(item,sort_keys=True,default=str).casefold()
            for token in ("usb","removable","mass-storage","sd card"))
        for item in attached if isinstance(item,Mapping)
    )
    context=exact.get("alertContext")
    description=str(context.get("description") or "") if isinstance(context,Mapping) else ""
    disk=re.search(r"\\Device\\Harddisk(\d+)\\DR(\d+)",description,re.IGNORECASE)
    # Removable hints do not prove the affected HarddiskX was removable.
    return HardwareTriageAssessment(
        playbook,"physical_disk_mapping_human_review",len(valid),
        protected,recurring,uid,disk.group(1) if disk else None,hints)
