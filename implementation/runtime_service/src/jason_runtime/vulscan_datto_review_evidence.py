"""Datto RMM as the only authoritative source of VulScan V2 patch holds.

Do not infer a technician's deliberate deferral from NOT_APPROVED alone:
automatic patch-policy filters and age windows can produce that state too.

This is a source-only, preproduction adapter over Jason's *existing governed*
read port. It never calls Datto directly, grants permission, patches endpoints,
or sends Teams messages. The complete policy Manual approval table must
ultimately be read and verified through an independently authorized Datto
policy capability; absent that port, negative evidence fails closed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from .vulscan_governed_patch_source import (
    VerifiedPatchTarget, VulscanPatchEvidenceError, _canonical_record,
)
from .vulscan_owner_disposition_evidence import VerifiedPatchReviewDisposition

_KB = re.compile(r"^KB[0-9]{5,9}$")
_UID = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_MAX_AGE = timedelta(minutes=15)
_DECISIONS = frozenset({"manual_not_approved", "no_manual_denial"})


class DattoManualReviewUnavailable(ValueError):
    """Datto manual denial, device override or negative coverage is unverified."""


@dataclass(frozen=True, slots=True)
class VerifiedDattoPolicyManualReview:
    """Independently complete, fresh Datto policy Manual approval attestation.

    no_manual_denial means the entire *manual* approved/not-approved/available
    table was read for this exact assigned policy and KB. The mere absence of
    KB from a filtered page or the automatic policy rules is not sufficient.

    This object is supplied by a separately governed, provider-backed Datto
    policy reader after schema, identity and pagination acceptance. It is not
    manufactured by this adapter from endpoint installStatus.
    """
    kb: str
    client_id: str
    site_uid: str
    device_uid: str
    policy_uid: str
    patch_id: str
    decision: str
    manual_table_complete: bool
    assigned_policy_verified: bool
    source_reference: str
    checked_at: datetime
    full_scope_verified: bool
    provider: str = "datto_rmm"


def verify_datto_manual_policy_review(
    proof: Any, *, target: VerifiedPatchTarget, patch_id: str, now: datetime,
) -> VerifiedDattoPolicyManualReview:
    """Reject inferred negative evidence, stale tables, and cross-client joins."""
    if not isinstance(proof, VerifiedDattoPolicyManualReview):
        raise DattoManualReviewUnavailable("Datto manual policy review evidence missing")
    if (proof.provider != "datto_rmm" or proof.kb != target.kb.upper()
            or proof.client_id != target.client_id
            or proof.site_uid != target.site_uid
            or proof.device_uid != target.device_uid
            or proof.policy_uid != target.policy_id
            or proof.patch_id != patch_id
            or not _UID.fullmatch(patch_id)):
        raise DattoManualReviewUnavailable("Datto policy review scope mismatch")
    if (proof.decision not in _DECISIONS
            or proof.manual_table_complete is not True
            or proof.assigned_policy_verified is not True
            or proof.full_scope_verified is not True
            or not isinstance(proof.source_reference, str)
            or not 0 < len(proof.source_reference.strip()) <= 250):
        raise DattoManualReviewUnavailable("Datto manual policy decision coverage incomplete")
    if (not isinstance(proof.checked_at, datetime)
            or proof.checked_at.tzinfo is None or now.tzinfo is None):
        raise DattoManualReviewUnavailable("Datto manual policy decision clock missing")
    age = now - proof.checked_at
    if age < timedelta(0) or age > _MAX_AGE:
        raise DattoManualReviewUnavailable("Datto manual policy decision stale or future dated")
    return proof


@dataclass
class DattoRmmPatchReviewReader:
    """Turn current Datto manual actions into exact scoped V2 dispositions.

    The existing governed endpoint.patch.search carries device-level
    manualOverride and effective installStatus. A separate, complete and
    authorized manual-approval policy table is required to prove the absence
    of a deliberate policy-wide denial. Neither automatic NOT_APPROVED nor
    manualOverride=False alone means an Owner accepted the patch.
    """
    governed_read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]]
    policy_manual_review_read: Callable[[VerifiedPatchTarget], VerifiedDattoPolicyManualReview]
    now: Callable[[], datetime]

    def __call__(self, target: VerifiedPatchTarget) -> VerifiedPatchReviewDisposition:
        current = self.now()
        if current.tzinfo is None:
            raise DattoManualReviewUnavailable("Datto review time must be timezone aware")
        if (not isinstance(target, VerifiedPatchTarget)
                or target.identity_verified is not True
                or target.policy_kb_attribution_verified is not True
                or not isinstance(target.site_uid, str)
                or not _UID.fullmatch(target.site_uid)
                or not _UID.fullmatch(target.policy_id)
                or not _UID.fullmatch(target.device_uid)
                or not _KB.fullmatch(target.kb.upper())):
            raise DattoManualReviewUnavailable("exact Datto review target identity unavailable")

        response = self.governed_read(
            "endpoint.patch.search",
            {"resource_id": target.device_uid, "kb": target.kb.upper(),
             "completeness_requirement": "complete"},
        )
        try:
            patch = _canonical_record(response, capability="endpoint.patch.search")
        except (VulscanPatchEvidenceError, ValueError, TypeError) as exc:
            raise DattoManualReviewUnavailable("exact governed Datto device patch missing") from exc
        evidence = response.get("evidence")
        if not isinstance(evidence, Mapping):
            raise DattoManualReviewUnavailable("governed Datto patch provenance missing")
        page = evidence.get("pageDetails")
        if (evidence.get("provider") != "datto_rmm"
                or evidence.get("provider_capability") != "datto_rmm.device.patches.list"
                or evidence.get("collection_key") != "patches"
                or evidence.get("bounded") is not False
                or not isinstance(page, Mapping)
                or page.get("nextPageUrl") not in (None, "")
                or evidence.get("ambiguous") is True
                or evidence.get("exact_selector_match") is False):
            raise DattoManualReviewUnavailable("Datto device patch page or scope incomplete")
        try:
            total = int(page["totalCount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DattoManualReviewUnavailable("Datto device patch total unavailable") from exc
        if total < 1:
            raise DattoManualReviewUnavailable("Datto device patch page contradictory")
        kb = str(patch.get("kbArticleId") or "").strip()
        if kb.lstrip("0") != target.kb[2:].lstrip("0"):
            raise DattoManualReviewUnavailable("Datto device patch KB identity mismatch")
        patch_id = str(patch.get("patchId") or "").strip()
        if not _UID.fullmatch(patch_id):
            raise DattoManualReviewUnavailable("exact Datto patch ID is missing")
        status = str(patch.get("installStatus") or "").strip().upper()
        if status != "NOT_APPROVED":
            raise DattoManualReviewUnavailable("Datto patch not in a reviewable NOT_APPROVED state")
        manual_override = patch.get("manualOverride")
        if type(manual_override) is not bool:
            raise DattoManualReviewUnavailable("Datto device manual override evidence unavailable")

        if manual_override is True:
            # The device-level UI explicitly overrode the patch's approval to
            # Do not approve. Do not claim a timed defer or a known Owner identity.
            return VerifiedPatchReviewDisposition(
                kb=target.kb.upper(), client_id=target.client_id,
                policy_id=target.policy_id, device_uid=target.device_uid,
                disposition="declined", checked_at=current,
                source_reference="datto_rmm:governed:endpoint.patch.search:device_manual_override",
                full_scope_verified=True,
            )

        # A false device override does NOT prove the policy's manual table has
        # no deliberate denial. The authoritative Datto policy list is required.
        try:
            manual = verify_datto_manual_policy_review(
                self.policy_manual_review_read(target),
                target=target, patch_id=patch_id, now=current,
            )
        except Exception as exc:
            raise DattoManualReviewUnavailable(
                "complete governed Datto policy Manual approval evidence unavailable"
            ) from exc
        return VerifiedPatchReviewDisposition(
            kb=target.kb.upper(), client_id=target.client_id,
            policy_id=target.policy_id, device_uid=target.device_uid,
            disposition=("declined" if manual.decision == "manual_not_approved"
                         else "review_pending"),
            checked_at=current,
            source_reference=manual.source_reference,
            full_scope_verified=True,
        )
