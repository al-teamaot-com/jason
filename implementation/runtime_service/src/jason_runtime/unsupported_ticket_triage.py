"""Bounded evidence-only triage for otherwise unsupported Autotask tickets.

This never admits work, chooses an unpromoted playbook, mutates a provider,
or claims a resolution. All provider reads are routed through the governed
read port, and device access requires exact same-company CI/UID evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
import json
import re


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


def _audit_disk_evidence(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract only non-sensitive, source-backed logical-disk metrics.

    Datto endpoint.audit.read returns the passive, authorized RMM audit.
    Free space is a snapshot; it is not evidence of current disk occupancy.
    Never infer large-directory usage or delete candidates from these metrics.
    """
    audit = data.get("audit")
    if not isinstance(audit, Mapping):
        audit = data
    disks = audit.get("logicalDisks")
    if not isinstance(disks, list):
        raise ValueError("disk_audit_missing")
    result: list[dict[str, Any]] = []
    if len(disks) > 32:
        raise ValueError("disk_audit_overflow")
    for disk in disks:
        if not isinstance(disk, Mapping):
            continue
        if str(disk.get("description") or "").strip().casefold() != "local fixed disk":
            continue
        drive = str(disk.get("diskIdentifier") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]:", drive):
            continue
        try:
            free = int(disk["freespace"])
            size = int(disk["size"])
        except (KeyError, ValueError, TypeError):
            continue
        if size <= 0 or free < 0 or free > size:
            continue
        result.append({
            "drive": drive, "free_bytes": free, "size_bytes": size,
            "free_percent": round(free * 100.0 / size, 1),
        })
    return sorted(result, key=lambda x: x["drive"])[:16]


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
    # Exclude the managed diagnostic note itself so its creation cannot
    # generate a changed note count and an unnecessary self-update loop.
    evidence["notes_observed"] = sum(
        1 for note in notes
        if not (
            isinstance(note, Mapping)
            and str(note.get("title") or "").strip()
            == "Jason - Governed Read-Only Investigation"
        )
    )

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
    if category == "disk_capacity":
        # The default worker identity does not have autonomous remote-code
        # execution authority. Passive RMM audits are sufficient to diagnose
        # current *audit-reported* disk capacity without a quick job.
        audit = read("endpoint.audit.read", {"resource_id": uid})
        disks = _audit_disk_evidence(audit)
        if not disks:
            return TriageResult(
                "needs_diagnostic_evidence", category, evidence,
                "Datto RMM audit has no verified local disk metrics. "
                "A technician may request separately authorized live diagnostics.",
            )
        evidence["disk_audit"] = disks
        last_audit = endpoint.get("last_audit") or endpoint.get("lastAudit")
        if isinstance(last_audit, str):
            evidence["audit_last_seen"] = last_audit[:48]
        return TriageResult(
            "read_only_assessed", category, evidence,
            "Disk capacity verified from a passive Datto RMM audit snapshot. "
            "Verify audit freshness and affected path before declaring an "
            "issue resolved or running any cleanup. " + next_step,
        )
    if category in ("windows_licensing", "rocketagent_service"):
        if "windows" not in operating_system:
            return TriageResult("diagnostic_not_applicable", category, evidence,
                                "OS is not verified as Windows. " + next_step)
        # A Datto PowerShell quick job is active endpoint execution, even if
        # its script is read-only. Never convert a diagnosis fallback into an
        # unapproved execution authority or repeatedly retry a denied action.
        return TriageResult(
            "needs_execution_authority", category, evidence,
            "The autonomous worker has no standing endpoint execution authority. "
            "A technician must run an approved read-only diagnostic or promote "
            "an exact, separately governed diagnostic playbook. " + next_step,
        )
    if category == "security_review":
        return TriageResult("needs_security_review", category, evidence, next_step)
    if category == "general":
        return TriageResult("needs_playbook_review", category, evidence, next_step)
    return TriageResult("read_only_assessed", category, evidence, next_step)


TRIAGE_NOTE_TITLE = "Jason - Governed Read-Only Investigation"


def render_triage_note(
    *,
    ticket_number: str,
    state: str,
    category: str,
    evidence: Mapping[str, Any],
    next_step: str,
) -> str:
    """Generate a bounded factual internal note draft, never a closure claim."""
    number = str(ticket_number or "").strip()[:48]
    if not re.fullmatch(r"T[0-9]{8}\.[0-9]{4}", number):
        number = "ticket-id verified in operational ledger"
    safe_states = {
        "read_only_assessed", "needs_device_identity", "needs_company_identity",
        "needs_security_review", "needs_playbook_review",
        "needs_execution_authority", "needs_diagnostic_evidence",
        "diagnostic_not_applicable", "device_availability_unknown",
        "waiting_device_access", "needs_human_review",
        "governance_blocked", "read_failed_retry",
    }
    normalized = str(state or "").strip()
    if normalized not in safe_states:
        raise ValueError("unsupported triage note state")
    allowed_categories = {
        "disk_capacity", "windows_licensing", "rocketagent_service",
        "security_review", "general",
    }
    if category not in allowed_categories:
        raise ValueError("unsupported triage note category")
    lines = [
        "JASON READ-ONLY INVESTIGATION",
        "Ticket: " + number,
        "Category: " + category.replace("_", " "),
        "Diagnostic outcome: " + normalized.replace("_", " "),
        "",
        "VERIFIED EVIDENCE",
    ]
    if evidence.get("company_verified") is True:
        lines.append("- Autotask ticket company association: verified")
    if evidence.get("rmm_identity_verified") is True:
        lines.append("- Exact same-company configuration/DRMM device: verified")
    if isinstance(evidence.get("online"), bool):
        lines.append("- DRMM online: " + ("Yes" if evidence["online"] else "No"))
    host = evidence.get("hostname")
    if isinstance(host, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", host):
        lines.append("- Device: " + host)
    count = evidence.get("notes_observed")
    if isinstance(count, int) and 0 <= count <= 100000:
        lines.append(f"- Existing notes observed: {count}")
    disks = evidence.get("disk_audit")
    if isinstance(disks, list):
        for disk in disks[:12]:
            if not isinstance(disk, Mapping):
                continue
            drive = str(disk.get("drive") or "").upper()
            try:
                size = int(disk.get("size_bytes"))
                free = int(disk.get("free_bytes"))
            except (TypeError, ValueError):
                continue
            if not re.fullmatch(r"[A-Z]:", drive) or size <= 0 or free < 0 or free > size:
                continue
            lines.append(
                f"- Datto audit volume {drive} {free / 1073741824:.1f} GiB free "
                f"of {size / 1073741824:.1f} GiB "
                f"({free / size * 100:.1f}% free)"
            )
        lines.append("- Disk values are a stored RMM audit snapshot, not live directory usage.")
    if len(lines) == 6:
        lines.append("- No additional independently verified device diagnostics.")
    lines.extend((
        "",
        "NEXT ACTION",
        # The next step originates from a fixed internal category mapping,
        # not an untrusted provider string.
        str(next_step or "").strip()[:650],
        "",
        "CHANGES MADE",
        "None. No files deleted, settings changed, endpoints restarted, "
        "tickets closed, or client messages sent.",
        "",
        "STATUS",
        "Not resolved or closed by this read-only investigation.",
    ))
    return "\n".join(lines)[:3200]
