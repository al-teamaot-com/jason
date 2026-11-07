"""Verified owner disposition for a specific Datto KB/policy/client/device.

Absence of a deferral can only be asserted by a separately governed,
scope-complete record. Empty provider collections and default False values
are NOT evidence that the Owner has not deferred or declined an update.

This module has no provider connections or release/send authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

_ALLOWED = frozenset({"review_pending", "deferred", "declined", "superseded"})
_MAX_AGE = timedelta(minutes=15)


class VulscanReviewDispositionUnavailable(ValueError):
    """Missing, stale, incomplete or contradictory owner decision evidence."""


@dataclass(frozen=True, slots=True)
class VerifiedPatchReviewDisposition:
    kb: str
    client_id: str
    policy_id: str
    device_uid: str
    disposition: str
    checked_at: datetime
    source_reference: str
    full_scope_verified: bool


def verify_patch_review_disposition(
    record: Any, *, kb: str, client_id: str, policy_id: str,
    device_uid: str, now: datetime,
) -> VerifiedPatchReviewDisposition:
    """Validate a fresh, exact source assertion, including negative evidence.

    review_pending is a positive attestation that the complete authorized
    decision source contained *no* active defer/decline/supersedence for this
    exact identity. A missing record or partial scope never means pending.
    """
    if not isinstance(record, VerifiedPatchReviewDisposition):
        raise VulscanReviewDispositionUnavailable("verified review record unavailable")
    if (record.kb != kb or record.client_id != client_id
            or record.policy_id != policy_id
            or record.device_uid != device_uid):
        raise VulscanReviewDispositionUnavailable("review record does not match exact scoped identity")
    if (record.full_scope_verified is not True
            or record.disposition not in _ALLOWED
            or not isinstance(record.source_reference, str)
            or not 0 < len(record.source_reference.strip()) <= 250):
        raise VulscanReviewDispositionUnavailable("authoritative decision coverage incomplete")
    if (not isinstance(record.checked_at, datetime)
            or record.checked_at.tzinfo is None or now.tzinfo is None):
        raise VulscanReviewDispositionUnavailable("decision clock provenance missing")
    age = now - record.checked_at
    if age < timedelta(0) or age > _MAX_AGE:
        raise VulscanReviewDispositionUnavailable("owner disposition read is stale or future dated")
    return record
