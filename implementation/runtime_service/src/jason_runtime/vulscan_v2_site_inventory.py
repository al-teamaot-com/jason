"""Build exact VulScan V2 targets from scoped, complete governed Datto reads.

An inventory is complete only if all authorized sites, patch pages, device
identities and assigned policy pages have independently verified readbacks.
No per-device Autotask CI or client association is inferred from ticket text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from .vulscan_governed_patch_source import (
    VerifiedPatchTarget, VulscanPatchEvidenceError,
)
from .vulscan_v2_preproduction_workflow import VerifiedVulscanTargetInventory
from .vulscan_policy_kb_attribution import (
    VerifiedPolicyKBAttribution, verified_unapproved_policy_ids,
    PolicyKBAttributionUnavailable,
)

_KB = re.compile(r"^[0-9]{5,9}$")
_UID = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_MAX_SITES = 80
_MAX_PATCHES = 6000
_MAX_DEVICES = 400
_MAX_TARGETS = 2500


@dataclass(frozen=True, slots=True)
class ApprovedDattoSiteScope:
    """Client association must come from existing authenticated site registry."""
    site_uid: str
    client_id: str
    client_binding_verified: bool


@dataclass(frozen=True, slots=True)
class ApprovedDattoSiteInventory:
    sites: tuple[ApprovedDattoSiteScope, ...]
    full_scope_verified: bool
    source_reference: str


def _records(response: Any, *, capability: str, collection_key: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(response, Mapping) or response.get("status") != "succeeded":
        raise VulscanPatchEvidenceError(f"governed {capability} unavailable")
    evidence = response.get("evidence")
    if not isinstance(evidence, Mapping):
        raise VulscanPatchEvidenceError(f"governed {capability} evidence missing")
    values = evidence.get("items")
    if not isinstance(values, list) or not all(isinstance(x, Mapping) for x in values):
        raise VulscanPatchEvidenceError(f"governed {capability} collection malformed")
    if evidence.get("bounded") is True:
        raise VulscanPatchEvidenceError(f"governed {capability} collection bounded/incomplete")
    meta = evidence.get("pageDetails")
    if not isinstance(meta, Mapping):
        raise VulscanPatchEvidenceError(f"governed {capability} pagination proof missing")
    try:
        total = int(meta["totalCount"])
    except (ValueError, TypeError, KeyError) as exc:
        raise VulscanPatchEvidenceError(f"governed {capability} total unknown") from exc
    if total != len(values) or meta.get("nextPageUrl") is not None:
        raise VulscanPatchEvidenceError(f"governed {capability} pagination incomplete")
    actual_key = evidence.get("collection_key")
    if actual_key is not None and actual_key != collection_key:
        raise VulscanPatchEvidenceError(f"governed {capability} wrong result kind")
    return tuple(values)


def collect_vulscan_v2_scoped_inventory(
    *, site_inventory: ApprovedDattoSiteInventory,
    read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    policy_attribution_read: Callable[[str, str, str, str], VerifiedPolicyKBAttribution] | None = None,
    now: datetime | None = None,
) -> VerifiedVulscanTargetInventory:
    """Only read, prove, and return exact targets. No Teams or ticket actions."""
    if (not isinstance(site_inventory, ApprovedDattoSiteInventory)
            or site_inventory.full_scope_verified is not True
            or not site_inventory.source_reference.strip()
            or not 0 < len(site_inventory.sites) <= _MAX_SITES):
        raise VulscanPatchEvidenceError("complete authorized Datto site scope not available")
    # A collection of assigned policy UIDs does not establish which policy
    # caused a KB's effective NOT_APPROVED status. Do not call Datto until the
    # bounded independent attribution reader and clock are present.
    if (policy_attribution_read is None or not isinstance(now, datetime)
            or now.tzinfo is None):
        raise VulscanPatchEvidenceError(
            "complete governed KB-to-policy attribution source unavailable")
    # Validate the WHOLE client-to-site mapping before any Datto read to
    # avoid partial cross-client access on a later invalid/duplicate site.
    seen_site: set[str] = set()
    for site in site_inventory.sites:
        if (not site.client_binding_verified
                or not _UID.fullmatch(site.site_uid)
                or not _UID.fullmatch(site.client_id)
                or site.site_uid in seen_site):
            raise VulscanPatchEvidenceError("unverified, invalid, or duplicate client/site scope")
        seen_site.add(site.site_uid)

    targets: dict[tuple[str, str, str, str], VerifiedPatchTarget] = {}
    processed_patches = 0
    processed_devices: set[str] = set()

    for site in sorted(site_inventory.sites, key=lambda s: s.site_uid):
        site_result = read("management.site.patch.search", {
            "resource_id": site.site_uid,
            "completeness_requirement": "complete",
        })
        records = _records(
            site_result, capability="management.site.patch.search",
            collection_key="patches")
        processed_patches += len(records)
        if processed_patches > _MAX_PATCHES:
            raise VulscanPatchEvidenceError("site patch inventory exceeds bounded run")

        by_device: dict[str, set[str]] = {}
        for patch in records:
            status = str(patch.get("installStatus") or "").upper().strip()
            numeric = str(patch.get("kbArticleId") or "").strip()
            if not _KB.fullmatch(numeric):
                # Driver/firmware/non-KB updates are not Windows KB aging items.
                continue
            if status != "NOT_APPROVED":
                continue
            uid = str(patch.get("deviceUid") or "").strip()
            if not _UID.fullmatch(uid):
                # Site-level patch aggregates without durable device identity
                # cannot establish client/device impact counts.
                raise VulscanPatchEvidenceError("site patch missing exact Datto device identity")
            by_device.setdefault(uid, set()).add("KB" + numeric)

        for uid, kbs in sorted(by_device.items()):
            processed_devices.add(uid)
            if len(processed_devices) > _MAX_DEVICES:
                raise VulscanPatchEvidenceError("device count exceeds bounded patch run")
            endpoint = read("endpoint.device.read", {"resource_id": uid})
            if (not isinstance(endpoint, Mapping)
                    or endpoint.get("status") != "succeeded"
                    or not isinstance(endpoint.get("evidence"), Mapping)
                    or not isinstance(endpoint["evidence"].get("record"), Mapping)):
                raise VulscanPatchEvidenceError("exact endpoint identity read unavailable")
            record = endpoint["evidence"]["record"]
            hostname = str(record.get("hostname") or "").strip()
            if (str(record.get("resource_id") or "") != uid
                    or str(record.get("site_id") or "") != site.site_uid
                    or not hostname or len(hostname) > 200):
                raise VulscanPatchEvidenceError("endpoint does not match verified managed site")
            policies_result = read("endpoint.patch.policy.search", {"resource_id": uid})
            policies = _records(
                policies_result, capability="endpoint.patch.policy.search",
                collection_key="policies")
            policy_ids = set()
            for policy in policies:
                policy_uid = str(policy.get("policyUid") or policy.get("uid") or "").strip()
                if not _UID.fullmatch(policy_uid):
                    raise VulscanPatchEvidenceError("assigned policy UID unavailable")
                policy_ids.add(policy_uid)
            if not policy_ids:
                raise VulscanPatchEvidenceError("unapproved KB has no verified assigned policy")
            for kb in sorted(kbs):
                try:
                    provenance = policy_attribution_read(site.site_uid, site.client_id, uid, kb)
                    attributable = verified_unapproved_policy_ids(
                        provenance, kb=kb, client_id=site.client_id,
                        site_uid=site.site_uid, device_uid=uid,
                        assigned_policy_ids=policy_ids, now=now,
                    )
                except Exception as exc:
                    raise VulscanPatchEvidenceError(
                        "governed KB-specific patch policy attribution unavailable"
                    ) from exc
                for policy_uid in attributable:
                    key = (kb, site.client_id, policy_uid, uid)
                    targets[key] = VerifiedPatchTarget(
                        kb=kb, client_id=site.client_id, policy_id=policy_uid,
                        device_id=uid, device_uid=uid, hostname=hostname,
                        identity_verified=True,
                        policy_kb_attribution_verified=True,
                        policy_kb_attribution_reference=provenance.source_reference,
                        policy_kb_attribution_checked_at=provenance.observed_at,
                    )
                    if len(targets) > _MAX_TARGETS:
                        raise VulscanPatchEvidenceError("KB/policy inventory exceeds bounded run")

    return VerifiedVulscanTargetInventory(
        targets=tuple(targets[key] for key in sorted(targets)),
        full_scope_verified=True, source_reference=site_inventory.source_reference,
    )
