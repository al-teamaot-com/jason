"""Deterministic, non-mutating Constant Contact import preflight.

Never infer marketing consent from an Excel row. This module cannot send HTTP
requests or create provider contacts; a separately governed executor must
revalidate a bound preview against current provider suppression state.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", re.ASCII)
FIELDS = frozenset({"email", "first_name", "last_name", "company_name", "job_title"})
CONSENT = frozenset({"explicit", "express"})
MAX_ROWS = 39999
MAX_EMAIL = 50


@dataclass(frozen=True)
class ImportPreflight:
    accepted: tuple[dict[str, str], ...]
    rejected: tuple[dict[str, str], ...]
    digest: str
    executable: bool


def preflight(
    rows: Iterable[Mapping[str, object]],
    *,
    consent_field: str = "marketing_consent",
    known_suppressed: Iterable[str] | None = None,
    suppression_inventory_complete: bool = False,
) -> ImportPreflight:
    """Build an advisory preview; never grant execution authority.

    A 'true' spreadsheet consent column is not enough: each accepted entry must
    also have documented consent evidence, represented by consent_evidence.
    Existing provider suppression must be checked separately before execution.
    """
    suppressed = {str(e).strip().casefold() for e in (known_suppressed or ())}
    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    consent_evidence_digests: list[dict[str, str]] = []
    for index, raw in enumerate(rows, start=2):
        if index > MAX_ROWS + 1:
            rejected.append({"row": str(index), "reason": "row_limit_exceeded"})
            continue
        email = str(raw.get("email") or "").strip().casefold()
        reason = None
        if not email or len(email) > MAX_EMAIL or not EMAIL.fullmatch(email):
            reason = "invalid_email"
        elif email in seen:
            reason = "duplicate_in_file"
        elif email in suppressed:
            reason = "provider_suppressed"
        elif str(raw.get(consent_field) or "").strip().casefold() not in CONSENT:
            reason = "explicit_marketing_consent_not_documented"
        elif not str(raw.get("consent_evidence") or "").strip():
            reason = "consent_evidence_missing"
        if email:
            seen.add(email)
        if reason:
            rejected.append({"row": str(index), "email": email, "reason": reason})
            continue
        contact = {"email": email}
        for field in sorted(FIELDS - {"email"}):
            value = str(raw.get(field) or "").strip()
            if value:
                if len(value) > 50:
                    reason = "field_too_long"
                    break
                contact[field] = value
        if reason:
            rejected.append({"row": str(index), "email": email, "reason": reason})
        else:
            accepted.append(contact)
            consent_evidence_digests.append({
                "email": email,
                "evidence_sha256": hashlib.sha256(str(raw["consent_evidence"]).strip().encode()).hexdigest(),
            })
    payload = {"accepted": accepted, "rejected": rejected,
               "consent_evidence_digests": consent_evidence_digests,
               "suppression_inventory_complete": suppression_inventory_complete}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ImportPreflight(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        digest=digest,
        executable=False,  # Advisory only: exact-action Teams approval and fresh provider readback are required.
    )
