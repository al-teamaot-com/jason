"""Pure read-only NDR evidence normalization; no mailbox/provider access."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Mapping

_STATUS = re.compile(r"(?<!\d)([245]\.\d{1,3}\.\d{1,3})(?!\d)")
_SIZE = re.compile(r"(?:message|attachment)\s+size\s*[:=]\s*(\d+)\s*(bytes|kb|mb|gb)", re.I)


@dataclass(frozen=True)
class NdrEvidence:
    tenant_id: str
    mailbox: str
    source_message_id: str
    failed_recipient: str | None
    original_message_id: str | None
    diagnostic_code: str | None
    reported_size_bytes: int | None
    received_at: str
    dedup_key: str
    source_kind: str = "synthetic_or_governed_mail"


def normalize_ndr(*, tenant_id: str, approved_mailbox: str, source: Mapping[str, str]) -> NdrEvidence:
    """Require an approved exact mailbox and preserve unknown fields as None."""
    tenant = tenant_id.strip().casefold()
    mailbox = approved_mailbox.strip().casefold()
    actual = str(source.get("mailbox", "")).strip().casefold()
    if not tenant or not mailbox or "@" not in mailbox or actual != mailbox:
        raise ValueError("exact approved tenant/mailbox context required")
    source_id = str(source.get("source_message_id", "")).strip()
    when = str(source.get("received_at", "")).strip()
    if not source_id or not when:
        raise ValueError("source message identifier and received timestamp required")
    diagnostic = str(source.get("diagnostic", ""))[:4096]
    status = _STATUS.search(diagnostic)
    size = _SIZE.search(diagnostic)
    factors = {"bytes": 1, "kb": 1024, "mb": 1048576, "gb": 1073741824}
    reported_size = int(size.group(1)) * factors[size.group(2).casefold()] if size else None
    recipient = str(source.get("failed_recipient", "")).strip().casefold() or None
    original = str(source.get("original_message_id", "")).strip() or None
    # Never conflate two tenants; duplicates can retain separate source IDs.
    stable = "|".join((tenant, mailbox, original or source_id, recipient or "", status.group(1) if status else ""))
    key = hashlib.sha256(stable.encode()).hexdigest()
    return NdrEvidence(tenant, mailbox, source_id, recipient, original,
                       status.group(1) if status else None, reported_size, when, key)


def correlate_exact(evidence: NdrEvidence, *, ticket_tenant: str, ticket_recipient: str | None) -> bool:
    """Only exact same-tenant recipient matches; ambiguous facts stay unlinked."""
    return bool(evidence.failed_recipient and ticket_recipient and
                evidence.tenant_id == ticket_tenant.strip().casefold() and
                evidence.failed_recipient == ticket_recipient.strip().casefold())
