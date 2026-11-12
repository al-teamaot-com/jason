"""Deterministic Constant Contact JSON import specification and status checks.

This module has NO provider transport and grants NO write authority. The final
governed executor must independently recheck live list IDs, unsubscriptions,
provider account binding and exact Teams approval before sending a request.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .import_preflight import ImportPreflight

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_ALLOWED_FIELDS = frozenset({"email", "first_name", "last_name", "company_name", "job_title"})
MAX_BODY_BYTES = 3_900_000


class ImportContractError(ValueError):
    """Safe error without source contact information."""


@dataclass(frozen=True)
class ImportSpecification:
    payload: dict[str, object]
    sha256: str
    contact_count: int
    list_ids: tuple[str, ...]
    preview_digest: str


def build_specification(preview: ImportPreflight, *, list_ids: Iterable[str]) -> ImportSpecification:
    """Create a stable proposal, NEVER a provider-write approval."""
    if not preview.accepted or preview.rejected:
        raise ImportContractError("Import preview contains no accepted rows or has rejected rows")
    selected = tuple(sorted(set(list_ids)))
    if not 1 <= len(selected) <= 50 or any(not _UUID.fullmatch(x) for x in selected):
        raise ImportContractError("Import list identifiers are invalid")
    if len(preview.accepted) > 39999:
        raise ImportContractError("Contact row limit exceeded")
    contacts: list[dict[str, str]] = []
    for contact in preview.accepted:
        if set(contact) - _ALLOWED_FIELDS or not contact.get("email"):
            raise ImportContractError("Unsupported import contact fields")
        contacts.append({key: str(value) for key, value in sorted(contact.items())})
    payload = {"import_data": contacts, "list_ids": list(selected)}
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(serialized) >= MAX_BODY_BYTES:
        raise ImportContractError("Import body exceeds safe size bound")
    return ImportSpecification(
        payload=payload,
        sha256=hashlib.sha256(serialized).hexdigest(),
        contact_count=len(contacts),
        list_ids=selected,
        preview_digest=preview.digest,
    )


def classify_activity(activity: Mapping[str, Any], *, expected_activity_id: str) -> dict[str, object]:
    """Fail closed on unknown, mismatched, errored or incomplete activity status."""
    if not _UUID.fullmatch(expected_activity_id):
        raise ImportContractError("Invalid activity identity")
    if str(activity.get("activity_id") or "").casefold() != expected_activity_id.casefold():
        raise ImportContractError("Activity ID mismatch")
    state = str(activity.get("state") or "").casefold()
    errors = activity.get("activity_errors")
    if not isinstance(errors, list):
        raise ImportContractError("Activity error evidence missing")
    try:
        progress = int(activity.get("percent_done"))
    except (ValueError, TypeError):
        raise ImportContractError("Activity progress is invalid") from None
    if not 0 <= progress <= 100:
        raise ImportContractError("Activity progress out of range")
    raw_counts = activity.get("status")
    counts = None
    if isinstance(raw_counts, Mapping):
        expected_keys = ("items_total_count", "items_completed_count",
                         "error_count", "cannot_add_to_list_count")
        if all(key in raw_counts for key in expected_keys):
            counts = {}
            for key in expected_keys:
                value = raw_counts[key]
                if type(value) is not int or value < 0:
                    raise ImportContractError("Provider activity counters invalid")
                counts[key] = value
    if errors:
        return {"state": "failed", "activity_id": expected_activity_id, "error_count": len(errors),
                "provider_counts": counts, "provider_readback_required": True}
    if progress == 100 and state in {"completed", "finished"} and activity.get("completed_at"):
        return {"state": "activity_complete_unverified", "activity_id": expected_activity_id,
                "provider_counts": counts, "provider_readback_required": True}
    if state in {"initialized", "processing", "running", "queued", "in_progress"}:
        return {"state": "pending", "activity_id": expected_activity_id,
                "provider_readback_required": True}
    return {"state": "unverified", "activity_id": expected_activity_id,
            "provider_readback_required": True}
