"""Deterministic evidence helpers for the Windows Unexpected Shutdown playbook."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

INCIDENT_WINDOW_MS = 15 * 60 * 1000
RECURRENCE_WINDOW_MS = 30 * 24 * 60 * 60 * 1000
SITE_ENVIRONMENTAL_MIN_PHYSICAL_DEVICES = 3

SHUTDOWN_EVENT_COMMAND = (
    "Get-WinEvent -FilterHashtable @{LogName='System'; "
    "Id=41,6008,6006,1074,1001,7,9,11,51,55,57,98,129,140,153,154,157; "
    "StartTime=(Get-Date).AddDays(-35)} -ErrorAction SilentlyContinue | "
    "Select-Object TimeCreated,Id,ProviderName,LevelDisplayName,Message | "
    "ConvertTo-Json -Compress"
)

WHEA_EVENT_COMMAND = (
    "Get-WinEvent -FilterHashtable @{LogName='System'; "
    "ProviderName='Microsoft-Windows-WHEA-Logger'; "
    "StartTime=(Get-Date).AddDays(-35)} -ErrorAction SilentlyContinue | "
    "Select-Object TimeCreated,Id,LevelDisplayName,Message | "
    "ConvertTo-Json -Compress"
)

PHYSICAL_DISK_COMMAND = (
    "Get-PhysicalDisk -ErrorAction SilentlyContinue | "
    "Select-Object FriendlyName,SerialNumber,MediaType,BusType,HealthStatus,"
    "OperationalStatus,Size | ConvertTo-Json -Compress"
)

RELIABILITY_COMMAND = (
    "Get-PhysicalDisk -ErrorAction SilentlyContinue | "
    "Get-StorageReliabilityCounter -ErrorAction SilentlyContinue | "
    "Select-Object Temperature,Wear,ReadErrorsTotal,WriteErrorsTotal,PowerOnHours | "
    "ConvertTo-Json -Compress"
)

VOLUME_HEALTH_COMMAND = (
    "Get-Volume -ErrorAction SilentlyContinue | "
    "Select-Object DriveLetter,FileSystem,FileSystemLabel,HealthStatus,"
    "OperationalStatus,SizeRemaining,Size | ConvertTo-Json -Compress"
)

STORAGE_RISK_EVENT_IDS = frozenset({7, 9, 11, 51, 55, 57, 98, 129, 140, 153, 154, 157})
CRASH_EVENT_IDS = frozenset({41, 1001})
CLEAN_SHUTDOWN_EVENT_IDS = frozenset({6006, 1074})


def _num(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def classify_site_scope(
    *,
    affected_physical_devices: int,
    active_physical_devices: int,
    ambiguous_physical_devices: int = 0,
) -> str:
    """Classify site correlation without overclaiming weak evidence."""
    affected = max(0, int(affected_physical_devices))
    active = max(0, int(active_physical_devices))
    ambiguous = max(0, int(ambiguous_physical_devices))
    if affected >= SITE_ENVIRONMENTAL_MIN_PHYSICAL_DEVICES:
        return "SITE_ENVIRONMENTAL"
    if affected == 1 and ambiguous == 0:
        return "DEVICE_SPECIFIC"
    if affected == 0:
        return "UNDETERMINED"
    # Two devices can be meaningful at a tiny site but are not enough by
    # themselves to assert a site-wide cause. Preserve the correlation ratio
    # as evidence and require another signal or technician judgment.
    if affected == 2 and active > 0 and affected == active and ambiguous == 0:
        return "SITE_CORRELATED_SMALL_SITE"
    return "UNDETERMINED"


def site_event_id(site: str, anchor_incident_ms: int, affected_device_ids: Sequence[str] = ()) -> str:
    # The caller supplies the earliest correlated physical-device event timestamp
    # as the anchor. Each independently processed ticket for the same site event
    # therefore converges on the same identity without relying on fragile wall-clock
    # bucket boundaries. Device IDs are intentionally excluded because discovery can
    # expand as additional endpoints report in.
    material = "|".join([
        str(site or "").strip().casefold(),
        str(int(anchor_incident_ms)),
    ])
    return "site-shutdown-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def storage_health_risk(
    *,
    events: Sequence[Mapping[str, Any]],
    whea_events: Sequence[Mapping[str, Any]],
    physical_disks: Sequence[Mapping[str, Any]],
    reliability: Sequence[Mapping[str, Any]],
    volumes: Sequence[Mapping[str, Any]],
) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    for event in events:
        try:
            event_id = int(event.get("Id"))
        except (TypeError, ValueError):
            continue
        if event_id in STORAGE_RISK_EVENT_IDS:
            reasons.append(f"storage event {event_id}")
    if whea_events:
        reasons.append(f"WHEA events={len(whea_events)}")
    for disk in physical_disks:
        health = str(disk.get("HealthStatus") or "").strip()
        operational = str(disk.get("OperationalStatus") or "").strip()
        if health and health.casefold() not in {"healthy", "unknown"}:
            reasons.append(f"disk health={health}")
        if any(token in operational.casefold() for token in ("degraded", "failed", "lost", "unhealthy")):
            reasons.append(f"disk operational={operational}")
    for item in reliability:
        reads = int(_num(item.get("ReadErrorsTotal")))
        writes = int(_num(item.get("WriteErrorsTotal")))
        if reads or writes:
            reasons.append(f"reliability read={reads} write={writes}")
    for volume in volumes:
        health = str(volume.get("HealthStatus") or "").strip()
        operational = str(volume.get("OperationalStatus") or "").strip()
        if health and health.casefold() not in {"healthy", "unknown"}:
            reasons.append(f"volume health={health}")
        if any(token in operational.casefold() for token in ("degraded", "failed", "unhealthy")):
            reasons.append(f"volume operational={operational}")
    unique = tuple(dict.fromkeys(reasons))
    return bool(unique), unique


def shutdown_character(events: Sequence[Mapping[str, Any]]) -> str:
    ids: set[int] = set()
    for item in events:
        try:
            ids.add(int(item.get("Id")))
        except (TypeError, ValueError):
            continue
    if 6008 in ids or 41 in ids:
        return "ABRUPT_OR_UNCLEAN"
    if ids & CLEAN_SHUTDOWN_EVENT_IDS:
        return "CLEAN_OR_PLANNED"
    return "UNDETERMINED"


def protected_role(endpoint: Mapping[str, Any]) -> bool:
    material = json.dumps(
        {
            "device_type": endpoint.get("device_type"),
            "operating_system": endpoint.get("operating_system") or endpoint.get("operatingSystem"),
        },
        sort_keys=True,
        default=str,
    ).casefold()
    return any(
        token in material
        for token in (
            "server",
            "domain controller",
            "hyper-v",
            "hyperv",
            "database",
            "backup repository",
            "physical host",
        )
    )
