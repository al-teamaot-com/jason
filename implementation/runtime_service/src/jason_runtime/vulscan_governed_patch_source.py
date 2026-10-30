"""Preproduction governed source reader for VulScan V2 patch observations.

All provider access is via an injected approved governed read port; no direct
Datto API, shell, HTTP, or credential access is implemented here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .vulscan_patch_approval_aging import PatchApprovalObservation
from .vulscan_patch_approval_notification import MicrosoftKBMetadata
from .vulscan_owner_disposition_evidence import (
    VerifiedPatchReviewDisposition, VulscanReviewDispositionUnavailable,
    verify_patch_review_disposition,
)

_KB = re.compile(r"^KB[0-9]{5,9}$")
_STATES = frozenset({"INSTALLED", "APPROVED_PENDING", "NOT_APPROVED", "INSTALL_ERROR", "FAILED"})
_MAX_TARGETS = 2500


class VulscanPatchEvidenceError(ValueError):
    """A required governed observation could not be proved."""


@dataclass(frozen=True, slots=True)
class VerifiedPatchTarget:
    """A target already linked to a same-client CI and exact Datto UID.

    This proof must come from a separately governed inventory/CI correlation.
    Do not manufacture this dataclass from untrusted VulScan ticket text.
    """
    kb: str
    client_id: str
    policy_id: str
    device_id: str
    device_uid: str
    hostname: str
    identity_verified: bool
    intentional_deferral: bool = False
    superseded: bool = False
    actively_exploited: bool = False
    exploitation_verified: bool = False
    # Separate positive proof that this policy, not merely the effective
    # device status or a second assigned policy, disapproved this exact KB.
    policy_kb_attribution_verified: bool = False
    policy_kb_attribution_reference: str = ""
    policy_kb_attribution_checked_at: datetime | None = None


def _canonical_record(value: Any, *, capability: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or value.get("status") != "succeeded":
        raise VulscanPatchEvidenceError(f"governed {capability} read failed")
    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping):
        raise VulscanPatchEvidenceError(f"governed {capability} evidence absent")
    if capability == "endpoint.device.read":
        result = evidence.get("record")
        if not isinstance(result, Mapping):
            raise VulscanPatchEvidenceError("endpoint identity readback absent")
        return result
    # Jason's live governed read service wraps collections as evidence.items.
    # Earlier test fixtures used evidence.data.patches/policies; accept both
    # but require one canonical, unambiguous exact-KB result.
    data = evidence.get("data")
    if data is not None and not isinstance(data, Mapping):
        raise VulscanPatchEvidenceError("provider data is malformed")
    if data is None:
        data = {}
    if capability == "endpoint.patch.policy.search":
        policies = evidence.get("items") if "items" in evidence else data.get("policies")
        if not isinstance(policies, list) or len(policies) > 200:
            raise VulscanPatchEvidenceError("authoritative patch-policy collection unavailable")
        details = evidence.get("pageDetails", data.get("pageDetails"))
        if details is not None:
            if not isinstance(details, Mapping):
                raise VulscanPatchEvidenceError("policy page metadata malformed")
            try:
                total = int(details.get("totalCount"))
            except (TypeError, ValueError) as exc:
                raise VulscanPatchEvidenceError("patch policy total missing") from exc
            if total != len(policies) or details.get("nextPageUrl"):
                raise VulscanPatchEvidenceError("patch policy pagination incomplete")
        if evidence.get("bounded") is True:
            raise VulscanPatchEvidenceError("truncated patch-policy read cannot prove completeness")
        uids = []
        for policy in policies:
            if not isinstance(policy, Mapping):
                raise VulscanPatchEvidenceError("patch policy record malformed")
            uid = str(policy.get("policyUid") or policy.get("uid") or "").strip()
            if not re.fullmatch(r"[A-Za-z0-9-]{1,100}", uid):
                raise VulscanPatchEvidenceError("patch policy durable UID missing")
            uids.append(uid)
        if len(uids) != len(set(uids)):
            raise VulscanPatchEvidenceError("duplicate patch policy")
        return {"policy_ids": tuple(uids)}
    results = evidence.get("items") if "items" in evidence else data.get("patches")
    if (not isinstance(results, list) or len(results) != 1
            or not isinstance(results[0], Mapping)
            or evidence.get("ambiguous") is True
            or evidence.get("exact_selector_match") is False
            or evidence.get("bounded") is True):
        raise VulscanPatchEvidenceError("exactly one unambiguous KB required")
    return results[0]


def collect_governed_patch_observations(
    *, targets: Iterable[VerifiedPatchTarget],
    metadata_by_kb: Mapping[str, MicrosoftKBMetadata],
    read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    now: datetime,
    review_disposition_read: Callable[[VerifiedPatchTarget], VerifiedPatchReviewDisposition] | None = None,
) -> tuple[PatchApprovalObservation, ...]:
    """Fail the entire batch on missing, ambiguous, or contradictory provider facts.

    Source coverage and site/client isolation are proven *before* calling this
    collector; each targeted endpoint is independently reread here.
    """
    if now.tzinfo is None:
        raise VulscanPatchEvidenceError("evaluation requires timezone-aware time")
    requested = tuple(targets)
    if not 0 < len(requested) <= _MAX_TARGETS:
        raise VulscanPatchEvidenceError("target list missing or exceeds bounded scan")
    seen: dict[tuple[str, str, str, str], VerifiedPatchTarget] = {}
    for target in requested:
        if not isinstance(target, VerifiedPatchTarget) or target.identity_verified is not True:
            raise VulscanPatchEvidenceError("missing verified CI/Datto association")
        checked = target.policy_kb_attribution_checked_at
        if (target.policy_kb_attribution_verified is not True
                or not isinstance(target.policy_kb_attribution_reference, str)
                or not 0 < len(target.policy_kb_attribution_reference.strip()) <= 250
                or not isinstance(checked, datetime) or checked.tzinfo is None
                or checked > now or (now - checked).total_seconds() > 900):
            raise VulscanPatchEvidenceError(
                "missing or stale exact KB-to-policy attribution proof")
        if (not _KB.fullmatch(target.kb.upper())
                or any(not str(v).strip() or len(str(v)) > 200
                       for v in (target.client_id, target.policy_id, target.device_id,
                                 target.device_uid, target.hostname))):
            raise VulscanPatchEvidenceError("unbounded or missing scoped target identity")
        key = (target.kb.upper(), target.client_id, target.policy_id, target.device_id)
        if key in seen and seen[key] != target:
            raise VulscanPatchEvidenceError("contradictory duplicate target")
        seen[key] = target

    # An incomplete/absent decision registry cannot attest the absence of an
    # Owner deferral. Reject before executing even read-only provider calls.
    if review_disposition_read is None:
        raise VulscanPatchEvidenceError("complete governed owner disposition source unavailable")
    observed_date = now.astimezone(ZoneInfo("America/New_York")).date()
    findings: list[PatchApprovalObservation] = []
    for key, target in sorted(seen.items()):
        kb = target.kb.upper()
        metadata = metadata_by_kb.get(kb)
        if (metadata is None or metadata.source_verified is not True
                or metadata.kb.upper() != kb):
            raise VulscanPatchEvidenceError("authoritative Microsoft KB release evidence missing")
        try:
            review = verify_patch_review_disposition(
                review_disposition_read(target),
                kb=kb, client_id=target.client_id,
                policy_id=target.policy_id, device_uid=target.device_uid,
                now=now,
            )
        except Exception as exc:
            raise VulscanPatchEvidenceError(
                "verified current owner deferral/decline coverage unavailable"
            ) from exc
        intentionally_deferred = review.disposition in {"deferred", "declined"}
        superseded = review.disposition == "superseded"
        if (target.intentional_deferral and not intentionally_deferred
                or target.superseded and not superseded):
            raise VulscanPatchEvidenceError("contradictory owner review disposition evidence")
        try:
            device_result = read("endpoint.device.read", {"resource_id": target.device_uid})
            endpoint = _canonical_record(device_result, capability="endpoint.device.read")
            if (str(endpoint.get("resource_id") or "") != target.device_uid
                    or str(endpoint.get("hostname") or "").casefold() != target.hostname.casefold()):
                raise VulscanPatchEvidenceError("Datto endpoint UID/hostname differs from verified CI")
            policies_result = read(
                "endpoint.patch.policy.search",
                {"resource_id": target.device_uid},
            )
            assigned = _canonical_record(policies_result, capability="endpoint.patch.policy.search")
            if target.policy_id not in assigned["policy_ids"]:
                raise VulscanPatchEvidenceError("exact device does not carry target patch policy")
            patches_result = read(
                "endpoint.patch.search",
                {"resource_id": target.device_uid, "kb": kb},
            )
            patch = _canonical_record(patches_result, capability="endpoint.patch.search")
        except VulscanPatchEvidenceError:
            raise
        except Exception as exc:
            raise VulscanPatchEvidenceError(
                "governed endpoint or patch read failed"
            ) from exc
        if str(patch.get("kbArticleId") or "").lstrip("0") != kb[2:].lstrip("0"):
            raise VulscanPatchEvidenceError("Datto patch object does not match exact KB")
        status = str(patch.get("installStatus") or "").strip().upper()
        if status not in _STATES:
            raise VulscanPatchEvidenceError("Datto patch state is not authoritative")
        findings.append(PatchApprovalObservation(
            kb=kb, release_date=metadata.release_date,
            observed_date=observed_date, policy_id=target.policy_id,
            client_id=target.client_id, device_id=target.device_id,
            approval_state=status, source_verified=True,
            intentional_deferral=intentionally_deferred,
            superseded=superseded,
            actively_exploited=target.actively_exploited,
            exploitation_verified=target.exploitation_verified,
        ))
    return tuple(findings)
