"""Deterministic evidence reduction for the Windows Low Disk Space playbook."""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

LOW_DISK_GRACE_SECONDS = 15 * 60
ONE_GIB = 1024 ** 3
SAFE_CLEANUP_MIN_BYTES = ONE_GIB

LARGE_ARTIFACT_EXTENSIONS = frozenset({
    ".iso", ".img", ".wim", ".esd", ".zip", ".7z", ".rar", ".cab",
    ".msi", ".msp", ".exe", ".dmp", ".vhd", ".vhdx", ".pst", ".ost",
})

TOP_FOLDER_COMMAND = (
    "Get-ChildItem C:\\ -Directory -Force -ErrorAction SilentlyContinue | "
    "Select-Object FullName,@{Name='Bytes';Expression={(Get-ChildItem $_.FullName "
    "-File -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum}} | "
    "Sort-Object Bytes -Descending | Select-Object -First 12 | ConvertTo-Json -Compress"
)

LARGE_FILE_COMMAND = (
    "Get-ChildItem C:\\ -File -Recurse -Force -ErrorAction SilentlyContinue | "
    "Sort-Object Length -Descending | Select-Object -First 30 FullName,Length,Extension,LastWriteTime | "
    "ConvertTo-Json -Compress"
)
VSS_COMMAND = (
    "Get-CimInstance Win32_ShadowStorage -ErrorAction SilentlyContinue | "
    "Select-Object Volume,DiffVolume,UsedSpace,AllocatedSpace,MaxSpace | ConvertTo-Json -Compress"
)

SYSTEM_FILE_COMMAND = (
    "Get-Item C:\\hiberfil.sys,C:\\pagefile.sys,C:\\MEMORY.DMP -Force "
    "-ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime | "
    "ConvertTo-Json -Compress"
)

PHYSICAL_DISK_COMMAND = (
    "Get-PhysicalDisk -ErrorAction SilentlyContinue | "
    "Select-Object FriendlyName,SerialNumber,MediaType,BusType,HealthStatus,OperationalStatus,Size | "
    "ConvertTo-Json -Compress"
)

RELIABILITY_COMMAND = (
    "Get-PhysicalDisk -ErrorAction SilentlyContinue | Get-StorageReliabilityCounter "
    "-ErrorAction SilentlyContinue | Select-Object Temperature,Wear,ReadErrorsTotal,"
    "WriteErrorsTotal,PowerOnHours | ConvertTo-Json -Compress"
)

SYSMON_COMMAND = (
    "Get-Item C:\\Sysmon -Force -ErrorAction SilentlyContinue | "
    "Select-Object FullName,@{Name='Bytes';Expression={(Get-ChildItem $_.FullName "
    "-File -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum}} | "
    "ConvertTo-Json -Compress"
)
SYSMON_DEPENDENCY_COMMAND = (
    "Get-CimInstance Win32_Service -ErrorAction SilentlyContinue | "
    "Where-Object PathName -Match 'C:\\\\Sysmon' | Select-Object Name,State,PathName | "
    "ConvertTo-Json -Compress"
)

SOFTWARE_DISTRIBUTION_COMMAND = (
    "Get-ChildItem C:\\Windows -Directory -Filter 'SoftwareDistribution.bak_*' "
    "-ErrorAction SilentlyContinue | Select-Object FullName,@{Name='Bytes';Expression={"
    "(Get-ChildItem $_.FullName -File -Recurse -Force -ErrorAction SilentlyContinue | "
    "Measure-Object Length -Sum).Sum}},LastWriteTime | ConvertTo-Json -Compress"
)


def parse_json_records(stdout: Any) -> list[dict[str, Any]]:
    text = str(stdout or "").strip()
    if not text:
        return []
    try:
        raw = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if isinstance(raw, Mapping):
        return [dict(raw)]
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, Mapping)]
    return []


def numeric(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def gib(value: Any) -> float:
    return numeric(value) / ONE_GIB


def _sum(records: Sequence[Mapping[str, Any]], key: str) -> float:
    return sum(numeric(item.get(key)) for item in records)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def storage_health_summary(
    physical_disks: Sequence[Mapping[str, Any]],
    reliability: Sequence[Mapping[str, Any]],
    storage_risk_hits: int,
) -> tuple[bool, str]:
    reasons: list[str] = []
    if storage_risk_hits:
        reasons.append(f"{storage_risk_hits} storage-health alert/event finding(s)")
    for disk in physical_disks:
        health = _safe_text(disk.get("HealthStatus")).casefold()
        operational = _safe_text(disk.get("OperationalStatus")).casefold()
        if health and health not in {"healthy", "unknown"}:
            reasons.append(f"physical disk health={_safe_text(disk.get('HealthStatus'))}")
        if any(token in operational for token in ("degraded", "failed", "lost", "unhealthy")):
            reasons.append(f"operational status={_safe_text(disk.get('OperationalStatus'))}")
    for item in reliability:
        read_errors = int(numeric(item.get("ReadErrorsTotal")))
        write_errors = int(numeric(item.get("WriteErrorsTotal")))
        if read_errors or write_errors:
            reasons.append(f"reliability errors read={read_errors} write={write_errors}")
    if reasons:
        return True, "; ".join(dict.fromkeys(reasons))[:500]
    if physical_disks:
        first = physical_disks[0]
        identity = " ".join(
            value for value in (
                _safe_text(first.get("FriendlyName")),
                _safe_text(first.get("MediaType")),
                _safe_text(first.get("BusType")),
            ) if value
        )
        return False, f"Healthy{': ' + identity if identity else ''}"
    return False, "No physical-disk health warning was returned"


def choose_cleanup(
    *,
    sysmon: Sequence[Mapping[str, Any]],
    sysmon_dependencies: Sequence[Mapping[str, Any]],
    software_distribution: Sequence[Mapping[str, Any]],
    storage_health_risk: bool,
) -> tuple[str | None, float]:
    if storage_health_risk:
        return None, 0.0
    sysmon_bytes = _sum(sysmon, "Bytes") if not sysmon_dependencies else 0.0
    software_bytes = _sum(software_distribution, "Bytes")
    choices = [
        ("sysmon", sysmon_bytes),
        ("software_distribution_backups", software_bytes),
    ]
    kind, amount = max(choices, key=lambda item: item[1])
    if amount < SAFE_CLEANUP_MIN_BYTES:
        return None, amount
    return kind, amount


def relevant_findings(
    *,
    top_folders: Sequence[Mapping[str, Any]],
    large_files: Sequence[Mapping[str, Any]],
    vss: Sequence[Mapping[str, Any]],
    system_files: Sequence[Mapping[str, Any]],
    sysmon: Sequence[Mapping[str, Any]],
    software_distribution: Sequence[Mapping[str, Any]],
    limit: int = 5,
) -> list[str]:
    findings: list[tuple[float, str]] = []
    for item in top_folders:
        amount = numeric(item.get("Bytes"))
        if amount >= ONE_GIB:
            findings.append((amount, f"{_safe_text(item.get('FullName'))} - {gib(amount):.1f} GB"))
    vss_bytes = _sum(vss, "UsedSpace")
    if vss_bytes >= ONE_GIB:
        findings.append((vss_bytes, f"VSS/shadow copies - {gib(vss_bytes):.1f} GB"))
    for item in system_files:
        amount = numeric(item.get("Length"))
        if amount >= ONE_GIB:
            findings.append((amount, f"{_safe_text(item.get('FullName'))} - {gib(amount):.1f} GB"))
    sysmon_bytes = _sum(sysmon, "Bytes")
    if sysmon_bytes >= ONE_GIB:
        findings.append((sysmon_bytes, f"C:\\Sysmon - {gib(sysmon_bytes):.1f} GB"))
    software_bytes = _sum(software_distribution, "Bytes")
    if software_bytes >= ONE_GIB:
        findings.append((software_bytes, f"SoftwareDistribution backup folders - {gib(software_bytes):.1f} GB"))
    for item in large_files:
        amount = numeric(item.get("Length"))
        extension = _safe_text(item.get("Extension")).casefold()
        if amount >= ONE_GIB and extension in LARGE_ARTIFACT_EXTENSIONS:
            findings.append((amount, f"{_safe_text(item.get('FullName'))} - {gib(amount):.1f} GB"))
    ordered: list[str] = []
    seen: set[str] = set()
    for _amount, text in sorted(findings, key=lambda item: item[0], reverse=True):
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)
        if len(ordered) >= limit:
            break
    return ordered


def recommendation(
    *,
    alert_still_open: bool,
    storage_health_risk: bool,
    cleanup_kind: str | None,
    cleanup_bytes: float,
    artifact_bytes: float,
) -> str:
    if storage_health_risk:
        return (
            "Drive replacement should be reviewed because storage-health evidence is present; "
            "select a larger capacity if the retained data footprint also requires it."
        )
    if cleanup_kind:
        label = (
            "orphaned C:\\Sysmon data"
            if cleanup_kind == "sysmon"
            else "old SoftwareDistribution backup folders"
        )
        return f"One approved cleanup can target {label} (~{gib(cleanup_bytes):.1f} GB), then recheck capacity."
    if artifact_bytes >= ONE_GIB:
        return (
            f"Large install/archive/image files total at least {gib(artifact_bytes):.1f} GB among the largest files. "
            "Confirm whether they are still required before deletion."
        )
    if alert_still_open:
        return (
            "No significant approved waste was identified. If the reported user/application data is expected, "
            "recommend replacing/upgrading the drive with a larger capacity."
        )
    return "Current monitor state is healthy; no capacity change is required from this incident."


def artifact_bytes(large_files: Sequence[Mapping[str, Any]]) -> float:
    return sum(
        numeric(item.get("Length"))
        for item in large_files
        if _safe_text(item.get("Extension")).casefold() in LARGE_ARTIFACT_EXTENSIONS
    )
