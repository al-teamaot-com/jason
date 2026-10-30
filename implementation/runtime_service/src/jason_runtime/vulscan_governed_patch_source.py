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
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        raise VulscanPatchEvidenceError("patch/policy read evidence absent")
    if capability == "endpoint.patch_policy.search":
        policies = data.get("policies")
        if not isinstance(policies, list) or len(policies) > 200:
            raise VulscanPatchEvidenceError("authoritative assigned patch policies not bounded")
        details = data.get("pageDetails")
        if isinstance(details, Mapping):
            try:
                total = int(details.get("totalCount"))
            except (TypeError, ValueError) as exc:
                raise VulscanPatchEvidenceError("patch policy total missing") from exc
            if total != len(policies):
                raise VulscanPatchEvidenceError("patch policy pagination incomplete")
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
    results = data.get("patches")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], Mapping):
        raise VulscanPatchEvidenceError("exactly one matching KB is required")
    return results[0]


def collect_governed_patch_observations(
    *, targets: Iterable[VerifiedPatchTarget],
    metadata_by_kb: Mapping[str, MicrosoftKBMetadata],
    read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    now: datetime,
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
        if (not _KB.fullmatch(target.kb.upper())
                or any(not str(v).strip() or len(str(v)) > 200
                       for v in (target.client_id, target.policy_id, target.device_id,
                                 target.device_uid, target.hostname))):
            raise VulscanPatchEvidenceError("unbounded or missing scoped target identity")
        key = (target.kb.upper(), target.client_id, target.policy_id, target.device_id)
        if key in seen and seen[key] != target:
            raise VulscanPatchEvidenceError("contradictory duplicate target")
        seen[key] = target

    observed_date = now.astimezone(ZoneInfo("America/New_York")).date()
    findings: list[PatchApprovalObservation] = []
    for key, target in sorted(seen.items()):
        kb = target.kb.upper()
        metadata = metadata_by_kb.get(kb)
        if (metadata is None or metadata.source_verified is not True
                or metadata.kb.upper() != kb):
            raise VulscanPatchEvidenceError("authoritative Microsoft KB release evidence missing")
        try:
            device_result = read("endpoint.device.read", {"resource_id": target.device_uid})
            endpoint = _canonical_record(device_result, capability="endpoint.device.read")
            if (str(endpoint.get("resource_id") or "") != target.device_uid
                    or str(endpoint.get("hostname") or "").casefold() != target.hostname.casefold()):
                raise VulscanPatchEvidenceError("Datto endpoint UID/hostname differs from verified CI")
            policies_result = read(
                "endpoint.patch_policy.search",
                {"resource_id": target.device_uid},
            )
            assigned = _canonical_record(policies_result, capability="endpoint.patch_policy.search")
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
            intentional_deferral=target.intentional_deferral,
            superseded=target.superseded,
            actively_exploited=target.actively_exploited,
            exploitation_verified=target.exploitation_verified,
        ))
    return tuple(findings)
