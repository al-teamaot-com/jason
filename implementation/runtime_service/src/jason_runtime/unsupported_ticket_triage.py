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


def category_for(title: str, unsupported_reason: str, description: str = "") -> str:
    """Classify bounded ticket context, not just an often-uninformative title.

    This controls read-only investigation only, never authorization to execute.
    """
    context = (str(title or "") + " " + str(description or "")[:12000]).casefold()
    if (
        any(term in context for term in ("licence", "license", "activation"))
        or unsupported_reason == "windows_licensing_diagnostics_candidate"
    ):
        return "windows_licensing"
    if "rocketagent" in context:
        return "rocketagent_service"
    if any(term in context for term in ("space issue", "disk space", "hard disk full")):
        return "disk_capacity"
    if any(term in context for term in (
        "threat", "edr", "security logs cleared",
        "linux logs cleared", "risky sign", "suspicious sign", "indirect command",
    )):
        return "security_review"
    if (
        ("network" in context and any(t in context for t in ("disconnect", "connectivity")))
        or ("screen" in context and any(t in context for t in ("timeout", "goes black", "sleep")))
        or any(t in context for t in ("sleep settings", "power settings"))
    ):
        return "user_device_settings"
    if any(t in context for t in (
        "microsoft 365", "office 365", "exchange online", "mailbox",
        "password reset", "conditional access", "mfa", "sign-in",
        "sign in", "account locked",
    )):
        return "account_service"
    if any(t in context for t in (
        "dhcp", "dns server", "firewall", "domain controller",
        "site outage", "server outage", "vpn gateway",
    )):
        return "infrastructure_service"
    return "general"


SCOPE_BY_CATEGORY = {
    "windows_licensing": "device",
    "rocketagent_service": "device",
    "disk_capacity": "device",
    "user_device_settings": "user_device",
    "account_service": "user_service",
    "infrastructure_service": "infrastructure",
    "security_review": "security",
    "general": "general",
}


NEXT_STEPS = {
    "account_service": (
        "Investigate the affected identity or service using governed account/service "
        "evidence; a device association is not required to begin. Apply an approved "
        "playbook or request only the specific missing facts."
    ),
    "infrastructure_service": (
        "Investigate the affected infrastructure/service and company scope. "
        "A workstation CI is not a prerequisite; provider changes remain governed."
    ),
    "user_device_settings": (
        "Correlate affected user, network disconnect timing, Windows power/screen policy, "
        "and recent update evidence. Resolve device identity against the same customer "
        "before endpoint diagnostics; do not modify power or network settings without "
        "the appropriate governed authority."
    ),
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
    ticket = ticket_snapshot
    category = category_for(title, unsupported_reason, str(ticket.get("description") or "") if isinstance(ticket, Mapping) else "")
    next_step = NEXT_STEPS[category]
    evidence: dict[str, Any] = {
        "ticket_id": ticket_id,
        "investigation_scope": SCOPE_BY_CATEGORY[category],
    }
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

    # Verify a linked contact under the explicit worker read policy. A temporary
    # failure in this optional association must not block unrelated safe reads.
    contact_raw = ticket.get("contactID")
    try:
        contact_id = int(contact_raw or 0)
    except (TypeError, ValueError):
        contact_id = 0
    if contact_id > 0:
        evidence["contact_associated"] = True
        evidence["contact_id"] = contact_id
        try:
            contact = _item(read("service.contact.read", {"resource_id": contact_id}))
        except Exception:
            evidence["contact_lookup_unavailable"] = True
        else:
            if (contact is None or _positive_id(contact.get("id")) != contact_id
                    or _positive_id(contact.get("companyID")) != actual_company):
                raise ValueError("contact_identity_unverified")
            evidence["contact_verified"] = True

    # Endpoints require exact same-company CI + UID evidence. User/service and
    # infrastructure investigations never require a workstation association.
    device_required = category in {
        "windows_licensing", "rocketagent_service", "disk_capacity",
    }
    if category in {"general", "account_service", "infrastructure_service", "security_review"}:
        state = "needs_security_review" if category == "security_review" else "needs_playbook_review"
        return TriageResult(
            state, category, evidence,
            "Company and available contact/note context assessed independently of any CI. " + next_step,
        )

    source_ci = ticket.get("configurationItemID")
    try:
        source_ci_id = int(source_ci or 0)
    except (TypeError, ValueError):
        source_ci_id = 0

    if source_ci_id == 0 and not configuration_item_id:
        if category == "user_device_settings":
            # A title is only a search hint. Never attach a CI or send endpoint
            # commands based on a textual hostname. Search within the company.
            hint = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]{3,63})\s*[-:]\s*", str(title or ""))
            if hint:
                candidate_name = hint.group(1)
                evidence["device_title_hint_unverified"] = candidate_name
                try:
                    candidate_data = read("service.configuration.search", {
                        "company_id": actual_company, "name": candidate_name,
                        "page_size": 25,
                    })
                    entries = candidate_data.get("items")
                    if not isinstance(entries, list):
                        raise ValueError("configuration_search_invalid")
                    evidence["same_company_ci_search_count"] = sum(
                        1 for entry in entries
                        if isinstance(entry, Mapping)
                        and int(entry.get("companyID") or 0) == actual_company
                        and str(entry.get("rmmDeviceAuditHostname") or entry.get("referenceTitle") or "").strip().casefold() == candidate_name.casefold()
                        and entry.get("isActive") is True
                    )
                except Exception:
                    evidence["ci_search_unavailable"] = True
            return TriageResult(
                "needs_diagnostic_evidence", category, evidence,
                "Continue user and configuration-policy investigation. A title hostname is "
                "unverified and no ticket CI is associated; only use a device after "
                "exact same-company CI/endpoint verification. " + next_step,
            )
        return TriageResult(
            "needs_device_identity", category, evidence,
            "Find and verify an exact same-company CI or endpoint before endpoint diagnostics. " + next_step,
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
        if category == "user_device_settings":
            return TriageResult("needs_diagnostic_evidence", category, evidence, next_step)
        return TriageResult("device_availability_unknown", category, evidence, next_step)
    evidence["online"] = online
    if not online:
        if category == "user_device_settings":
            return TriageResult("needs_diagnostic_evidence", category, evidence,
                                "Device offline; continue user/policy investigation without endpoint execution. " + next_step)
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
    if category == "user_device_settings":
        return TriageResult(
            "needs_diagnostic_evidence", category, evidence,
            "Endpoint identity verified, but live policy/network diagnosis requires "
            "separately authorized evidence collection. " + next_step,
        )
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
        "security_review", "general", "user_device_settings",
        "account_service", "infrastructure_service",
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
    scope = evidence.get("investigation_scope")
    if isinstance(scope, str) and scope in set(SCOPE_BY_CATEGORY.values()):
        lines.append("- Investigation scope: " + scope.replace("_", " "))
    if evidence.get("contact_verified") is True:
        lines.append("- Autotask contact and company association: verified")
    elif evidence.get("contact_lookup_unavailable") is True:
        lines.append("- Ticket contact linked; governed contact lookup unavailable")
    host_hint = evidence.get("device_title_hint_unverified")
    if isinstance(host_hint, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{3,63}", host_hint):
        lines.append("- Title-only device hint (UNVERIFIED): " + host_hint)
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
