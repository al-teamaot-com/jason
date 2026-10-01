from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

BASE_TITLE = "GPT Insights"
UPDATE_PREFIX = "GPT Insights - Update"
AUGMENTATION_ID = "gpt_insights_tech_assist_v0_1"

NETWORK_COMMAND = (
    "$up=Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object Status -eq 'Up'; "
    "$profiles=Get-NetConnectionProfile -ErrorAction SilentlyContinue; "
    "$up | Select-Object Name,InterfaceDescription,MediaType,PhysicalMediaType,LinkSpeed,MacAddress,@{n='Profile';e={($profiles | Where-Object InterfaceAlias -eq $_.Name | Select-Object -First 1 -ExpandProperty Name)}} | ConvertTo-Json -Compress"
)

CATEGORY_COMMANDS = {
    "network": (
        "Get-NetAdapter | Format-Table Name,Status,LinkSpeed,MacAddress -Auto",
        "Get-NetIPConfiguration",
        "Test-NetConnection 8.8.8.8",
        "Resolve-DnsName microsoft.com",
    ),
    "performance": (
        "Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 Name,CPU,WorkingSet",
        "Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime,FreePhysicalMemory,TotalVisibleMemorySize",
    ),
    "printing": (
        "Get-Printer | Select-Object Name,DriverName,PortName,PrinterStatus",
        "Get-Service Spooler | Select-Object Status,StartType",
    ),
    "login": (
        "whoami /all",
        "Get-WinEvent -FilterHashtable @{LogName='System';StartTime=(Get-Date).AddHours(-24)} | Select-Object -First 50 TimeCreated,Id,ProviderName,Message",
    ),
    "application": (
        "Get-Process | Sort-Object ProcessName | Select-Object ProcessName,Id,CPU,WorkingSet",
        "Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=(Get-Date).AddHours(-24);Level=2,3} | Select-Object -First 50 TimeCreated,Id,ProviderName,Message",
    ),
}

@dataclass(frozen=True, slots=True)
class InsightEvidence:
    category: str
    ticket_number: str
    ticket_title: str
    device_name: str | None = None
    device_online: bool | None = None
    last_seen: str | None = None
    operating_system: str | None = None
    connection_summary: str | None = None
    related_ticket_count: int = 0
    related_ticket_titles: tuple[str, ...] = ()
    site_correlation: str | None = None
    unresolved_reason: str | None = None


def classify_ticket(title: str, description: str) -> str:
    text = f"{title} {description}".casefold()
    families = (
        ("network", ("wifi", "wi-fi", "internet", "network", "disconnect", "connection", "ethernet", "dns", "dhcp")),
        ("printing", ("print", "printer", "scan", "spooler")),
        ("performance", ("slow", "freeze", "freezing", "hang", "performance", "cpu", "memory")),
        ("login", ("login", "log in", "sign in", "password", "locked out", "credential")),
        ("application", ("app", "application", "program", "software", "crash", "error")),
    )
    for category, tokens in families:
        if any(token in text for token in tokens):
            return category
    return "unknown"


def connection_summary(records: Sequence[Mapping[str, Any]]) -> str | None:
    active: list[str] = []
    for item in records:
        name = str(item.get("Name") or item.get("name") or "").strip()
        media = " ".join(
            str(item.get(key) or "")
            for key in ("MediaType", "PhysicalMediaType", "InterfaceDescription")
        ).casefold()
        profile = str(item.get("Profile") or "").strip()
        if not name:
            continue
        kind = "Wi-Fi" if any(token in media for token in ("wireless", "802.11", "wi-fi", "wifi")) else "Wired" if any(token in media for token in ("ethernet", "802.3")) else "Active adapter"
        suffix = f" ({profile})" if profile else ""
        active.append(f"{kind}: {name}{suffix}")
    return "; ".join(active) if active else None


def material_fingerprint(evidence: InsightEvidence) -> str:
    payload = {
        "category": evidence.category,
        "device_name": evidence.device_name,
        "device_online": evidence.device_online,
        "last_seen": evidence.last_seen,
        "operating_system": evidence.operating_system,
        "connection_summary": evidence.connection_summary,
        "related_ticket_count": evidence.related_ticket_count,
        "related_ticket_titles": evidence.related_ticket_titles,
        "site_correlation": evidence.site_correlation,
        "unresolved_reason": evidence.unresolved_reason,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def note_title(*, update: bool, now: datetime | None = None) -> str:
    if not update:
        return BASE_TITLE
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"{UPDATE_PREFIX} {stamp}"


def render_insight(evidence: InsightEvidence) -> str:
    lines = ["GPT Insights", "", "Current evidence"]
    if evidence.device_name:
        state = "online" if evidence.device_online is True else "offline" if evidence.device_online is False else "state unavailable"
        lines.append(f"- Device: {evidence.device_name} ({state}).")
    else:
        lines.append("- No device could be confidently associated from current ticket evidence.")
    if evidence.last_seen:
        lines.append(f"- Last seen: {evidence.last_seen}.")
    if evidence.operating_system:
        lines.append(f"- OS: {evidence.operating_system}.")
    if evidence.connection_summary:
        lines.append(f"- Active connection evidence: {evidence.connection_summary}.")
    if evidence.related_ticket_count:
        titles = "; ".join(evidence.related_ticket_titles[:3])
        lines.append(f"- Related recent tickets found: {evidence.related_ticket_count}" + (f" ({titles})." if titles else "."))
    if evidence.site_correlation:
        lines.append(f"- Site correlation: {evidence.site_correlation}")

    lines.extend(["", "Assessment"])
    if evidence.category == "unknown":
        lines.append("- Jason could not confidently classify the reported request from the available evidence. No cause is asserted.")
    else:
        lines.append(f"- Ticket appears to involve {evidence.category} troubleshooting. This is guidance, not a confirmed root cause.")
    if evidence.unresolved_reason:
        lines.append(f"- Limitation: {evidence.unresolved_reason}")

    lines.extend(["", "Recommended next steps"])
    if evidence.category == "network":
        lines.extend([
            "- Compare the user's reported time with adapter, DHCP/DNS, gateway, and site-wide evidence before changing configuration.",
            "- If current adapter evidence already establishes wired vs Wi-Fi, do not ask the technician or user to rediscover it.",
        ])
    elif evidence.category == "printing":
        lines.append("- Confirm printer visibility, queue state, port/driver assignment, and spooler health before reinstalling anything.")
    elif evidence.category == "performance":
        lines.append("- Check uptime, top CPU/memory consumers, free memory, and recent System/Application errors before restarting or rebooting.")
    elif evidence.category == "login":
        lines.append("- Correlate the affected identity, endpoint state, recent authentication/system events, and known account state before resetting credentials.")
    elif evidence.category == "application":
        lines.append("- Confirm whether the process is running and review recent application errors before repair/reinstall actions.")
    else:
        lines.append("- Review the request with the client only for information Jason cannot obtain from available systems. Do not ask for discoverable facts.")

    commands = CATEGORY_COMMANDS.get(evidence.category, ())
    if commands:
        lines.extend(["", "Useful read-only PowerShell"])
        lines.extend(f"- {command}" for command in commands)
    return "\n".join(lines).strip()
