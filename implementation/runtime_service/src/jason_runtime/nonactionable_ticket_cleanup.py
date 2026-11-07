"""Strict, deterministic administrative classification; never a grant of authority.

No LLM confidence, sender-domain inference, URLs, unsubscribe clicks, endpoint
actions, security reports, vendor operational reports or payment notices.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Any


@dataclass(frozen=True)
class CleanupDecision:
    category: str
    reason: str


_MARKETING_SENDER = re.compile(
    r'^From\s+"?Network Solutions"?\s*<info@eml\.networksolutions\.com>\s*:',
    re.IGNORECASE,
)
_PROMOTION = re.compile(
    r'(?:(?:\d{1,2}|100)\s*%\s*off\b|save\s+(?:up\s+to\s+)?\d{1,2}\s*%\b)',
    re.IGNORECASE,
)
_AUTO_REPLY = re.compile(r'^automatic reply:\s*\S', re.IGNORECASE)
_AUTO_BODY = re.compile(
    r'\b(?:out of the office|out of office|on vacation|away from the office)\b',
    re.IGNORECASE,
)
_TICKET_REFERENCE = re.compile(r'\bT\d{8}\.\d{4}(?:\.\d+)?\b', re.IGNORECASE)
_UNSAFE_SUBJECT = re.compile(
    r'\b(?:invoice|receipt|payment|refund|renewal|expiration|expired|'
    r'billing|suspension|alert|breach|phishing|malware|ticket|support|'
    r'delivery failure|undeliverable|bounce|cancellation)\b',
    re.IGNORECASE,
)


def classify(ticket: Mapping[str, Any]) -> CleanupDecision | None:
    """Return a disposal candidate, not permission to update a ticket."""
    if not isinstance(ticket, Mapping):
        return None
    try:
        source = int(ticket.get("source") or 0)
    except (TypeError, ValueError):
        return None
    if source != 4:  # Autotask Source=Email, not Phone or Monitoring Alert
        return None
    subject = str(ticket.get("title") or "").strip()[:250]
    body = str(ticket.get("description") or "")[:14000]
    if not subject or not body or _UNSAFE_SUBJECT.search(subject):
        return None
    if _TICKET_REFERENCE.search(subject) or _TICKET_REFERENCE.search(body):
        return None
    if _MARKETING_SENDER.match(body) and _PROMOTION.search(subject):
        return CleanupDecision("verified_vendor_promotion", "Exact promotional sender and offer subject")
    if (_AUTO_REPLY.match(subject) and _AUTO_BODY.search(body[:2000])
            and not ticket.get("configurationItemID")):
        return CleanupDecision("out_of_office_auto_reply", "Explicit automatic-reply subject and absence wording")
    return None


def identity_ready(ticket: Mapping[str, Any]) -> bool:
    """Site is required. No endpoint/user is needed for administrative cleanup."""
    try:
        return (
            int(ticket.get("id") or 0) > 0
            and int(ticket.get("companyID") or 0) > 0
            and int(ticket.get("companyLocationID") or 0) > 0
            and ticket.get("configurationItemID") in (None, "", 0, "0")
        )
    except (TypeError, ValueError):
        return False


def only_system_notes(notes: list[Mapping[str, Any]]) -> bool:
    """Fail closed when a technician or client has interacted with the ticket."""
    if len(notes) > 100:
        return False
    return all(
        isinstance(note, Mapping)
        and note.get("createdByContactID") in (None, "", 0)
        and note.get("creatorResourceID") == 4
        and note.get("noteType") in (2, 13, 91, 99)
        for note in notes
    )
