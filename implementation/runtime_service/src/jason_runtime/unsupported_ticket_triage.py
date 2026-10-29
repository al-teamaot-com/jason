"""Bounded evidence-only triage for otherwise unsupported Autotask tickets.

This never admits work, chooses an unpromoted playbook, mutates a provider,
or claims a resolution. All provider reads are routed through the governed
read port, and device access requires exact same-company CI/UID evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
import json


WINDOWS_LICENSING_READ = (
    "$ErrorActionPreference='Stop'; "
    "Get-CimInstance -ClassName SoftwareLicensingProduct "
    "-Filter 'PartialProductKey IS NOT NULL' | "
    "Where-Object {$_.Name -like 'Windows*'} | "
    "Select-Object -First 4 Name,LicenseStatus | ConvertTo-Json -Compress"
)
WINDOWS_SERVICE_READ = (
    "$ErrorActionPreference='Stop'; "
    "Get-Service -Name RocketAgent -ErrorAction SilentlyContinue | "
    "Select-Object Name,Status,StartType | ConvertTo-Json -Compress"
)
WINDOWS_DISK_READ = (
    "$ErrorActionPreference='Stop'; "
    "Get-CimInstance -ClassName Win32_LogicalDisk -Filter 'DriveType=3' | "
    "Select-Object DeviceID,FreeSpace,Size | ConvertTo-Json -Compress"
)
READ_COMMANDS = {
    "windows_licensing": WINDOWS_LICENSING_READ,
    "rocketagent_service": WINDOWS_SERVICE_READ,
    "disk_capacity": WINDOWS_DISK_READ,
}


@dataclass(frozen=True)
class TriageResult:
    state: str
    category: str
    evidence: Mapping[str, Any]
    next_step: str


def category_for(title: str, unsupported_reason: str) -> str:
    """Choose a fixed, read-only diagnostic; never synthesize a shell command."""
    title = str(title or "").casefold()
    if (
        "licence" in title or "license" in title or "activation" in title
        or unsupported_reason == "windows_licensing_diagnostics_candidate"
    ):
        return "windows_licensing"
    if "rocketagent" in title:
        return "rocketagent_service"
    if "space issue" in title or "disk space" in title or "hard disk full" in title:
        return "disk_capacity"
    if any(term in title for term in (
        "threat", "edr", "security logs cleared", "linux logs cleared",
        "risky sign", "suspicious sign", "indirect command",
    )):
        return "security_review"
    return "general"


NEXT_STEPS = {
    "windows_licensing": (
        "Validate Windows activation and entitlement. A non-licensed status "
        "is diagnostic evidence, not permission to change licensing."
    ),
    "rocketagent_service": (
        "Correlate current RocketAgent service status and vendor evidence; "
        "service restarts require the applicable governed approval."
    ),
    "disk_capacity": (
        "Review disk free-space evidence and approved cleanup runbooks; "
        "do not delete files or change configuration from this triage."
    ),
    "security_review": (
        "Security technician must correlate provider detection/identity "
        "evidence before classifying benign or malicious activity."
    ),
    "general": (
        "Identify an approved playbook or collect the missing technician/client "
        "facts; this diagnostic does not authorize remediation."
    ),
}


def _item(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    record = data.get("record")
    if isinstance(record, Mapping):
        return record
    items = data.get("items")
    if isinstance(items, list) and len(items) == 1 and isinstance(items[0], Mapping):
        return items[0]
    value = data.get("item")
    if isinstance(value, Mapping):
        return value
    return None


def _positive_id(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("identity_missing") from exc
    if number <= 0:
        raise ValueError("identity_missing")
    return number


def _read_command_evidence(data: Mapping[str, Any], category: str) -> list[dict[str, Any]]:
    """Retain only allowlisted telemetry; no arbitrary stdout or secrets."""
    raw = data.get("stdout") or data.get("text")
    if not isinstance(raw, str) or not raw.strip():
        return []
    parsed = json.loads(raw)
    rows = parsed if isinstance(parsed, list) else [parsed]
    if len(rows) > 20 or not all(isinstance(row, dict) for row in rows):
        raise ValueError("diagnostic_output_invalid")
    permitted = {
        "windows_licensing": ("Name", "LicenseStatus"),
        "rocketagent_service": ("Name", "Status", "StartType"),
        "disk_capacity": ("DeviceID", "FreeSpace", "Size"),
    }[category]
    cleaned = []
    for row in rows:
        values: dict[str, Any] = {}
        for key in permitted:
            value = row.get(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                values[key] = value if not isinstance(value, str) else value[:120]
        cleaned.append(values)
    return cleaned


def gather(
    *,
    ticket_id: int,
    company_id: int,
    configuration_item_id: int | None,
    ticket_snapshot: Mapping[str, Any],
    title: str,
    unsupported_reason: str,
    read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
) -> TriageResult:
    """Verify authoritative queue-search snapshot; run only allowed governed reads.

    The production worker read policy intentionally denies service.ticket.read.
    Queue discovery has already fetched the current ticket using the governed
    service.ticket.search capability; use that exact snapshot rather than
    silently requiring any new information-release authority.
    """
    ticket_id = _positive_id(ticket_id)
    category = category_for(title, unsupported_reason)
    next_step = NEXT_STEPS[category]
    evidence: dict[str, Any] = {"ticket_id": ticket_id}
    ticket = ticket_snapshot
    if not isinstance(ticket, Mapping) or _positive_id(ticket.get("id")) != ticket_id:
        raise ValueError("ticket_readback_mismatch")
    # Missing company on an otherwise real ticket is a human identity gap,
    # not grounds to infer a tenant from a CI or hostname.
    if not ticket.get("companyID") or int(company_id or 0) <= 0:
        return TriageResult(
            "needs_company_identity", category, evidence,
            "Verify the customer/company association in Autotask. " + next_step,
        )
    actual_company = _positive_id(ticket.get("companyID"))
    if actual_company != _positive_id(company_id):
        raise ValueError("ticket_company_mismatch")
    evidence["company_verified"] = True

    # Note history is context, not an automatic finding that a ticket is resolved.
    notes = read("service.ticket.notes.search", {"ticket_id": ticket_id}).get("items")
    if not isinstance(notes, list):
        raise ValueError("notes_readback_invalid")
    evidence["notes_observed"] = len(notes)

    source_ci = ticket.get("configurationItemID")
    source_ci_id = int(source_ci or 0)
    if source_ci_id == 0 and not configuration_item_id:
        return TriageResult(
            "needs_device_identity", category, evidence,
            "Associate an exact same-company CI; " + next_step,
        )
    if not source_ci_id or source_ci_id != int(configuration_item_id or 0):
        raise ValueError("ticket_ci_mismatch")

    ci = _item(read("service.configuration.read", {"resource_id": source_ci_id}))
    if (
        ci is None
        or _positive_id(ci.get("id")) != source_ci_id
        or _positive_id(ci.get("companyID")) != actual_company
        or ci.get("isActive") is not True
    ):
        raise ValueError("configuration_identity_unverified")
    uid = str(ci.get("referenceNumber") or "").strip()
    if not uid:
        return TriageResult("needs_device_identity", category, evidence,
                            "CI has no exact RMM UID. " + next_step)

    endpoint_data = read("endpoint.device.read", {"resource_id": uid})
    endpoint = _item(endpoint_data) or endpoint_data
    endpoint_uid = str(
        endpoint.get("resource_id") or endpoint.get("uid") or endpoint.get("deviceUid") or ""
    ).strip()
    if endpoint_uid != uid:
        raise ValueError("endpoint_identity_mismatch")
    ci_host = str(ci.get("rmmDeviceAuditHostname") or ci.get("dattoHostname") or "").strip()
    endpoint_host = str(
        endpoint.get("hostname") or endpoint.get("hostName") or endpoint.get("name") or ""
    ).strip()
    if ci_host and endpoint_host and ci_host.casefold() != endpoint_host.casefold():
        raise ValueError("endpoint_hostname_mismatch")
    evidence["rmm_identity_verified"] = True
    evidence["hostname"] = (endpoint_host or ci_host)[:128]
    online = endpoint.get("online")
    if not isinstance(online, bool):
        return TriageResult("device_availability_unknown", category, evidence, next_step)
    evidence["online"] = online
    if not online:
        return TriageResult("waiting_device_access", category, evidence, next_step)

    operating_system = str(
        endpoint.get("operatingSystem") or endpoint.get("operating_system") or ""
    ).strip().casefold()
    if category in READ_COMMANDS:
        if "windows" not in operating_system:
            return TriageResult("diagnostic_not_applicable", category, evidence,
                                "OS is not verified as Windows. " + next_step)
        try:
            output = read(
                "endpoint.powershell.read",
                {"device_uid": uid, "command": READ_COMMANDS[category], "timeout_seconds": 45},
            )
            evidence["diagnostic"] = _read_command_evidence(output, category)
        except (ValueError, TypeError):
            raise ValueError("diagnostic_output_invalid") from None
    if category == "security_review":
        return TriageResult("needs_security_review", category, evidence, next_step)
    if category == "general":
        return TriageResult("needs_playbook_review", category, evidence, next_step)
    return TriageResult("read_only_assessed", category, evidence, next_step)
