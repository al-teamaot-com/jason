"""Read-only site patch coverage from existing governed Datto device reads.

This is an explicitly injected preproduction alternative when the newer Datto
site-patch endpoint is unavailable. It is not a direct provider adapter and
never claims that an account-wide discovery result is complete without the
governed search proof and exact site UID on every returned device.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from .vulscan_governed_patch_source import VulscanPatchEvidenceError
from .vulscan_v2_site_inventory import (
    ApprovedDattoSiteScope, VerifiedDattoSitePatchCollection,
)

_UID = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_KB = re.compile(r"^[0-9]{5,9}$")
_MAX_DEVICES = 400
_MAX_PATCHES = 6000
_MAX_AGE = timedelta(minutes=15)


def collect_governed_site_patches_from_devices(
    *, site: ApprovedDattoSiteScope, site_name: str,
    read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    now: datetime,
    max_devices: int = _MAX_DEVICES,
    max_patches: int = _MAX_PATCHES,
) -> VerifiedDattoSitePatchCollection:
    """Require fully scoped discovery and complete device patch pagination.

    The result contains only *observed* NOT_APPROVED Windows KBs; it does not
    assign a causing policy, interpret deliberate denial, or authorize Teams.
    Complete zero-result sites remain valid only if at least one managed device
    was independently discovered and every device patch read succeeded.
    """
    if (not isinstance(site, ApprovedDattoSiteScope)
            or site.client_binding_verified is not True
            or not _UID.fullmatch(site.site_uid)
            or not _UID.fullmatch(site.client_id)
            or not isinstance(site_name, str)
            or not 0 < len(site_name.strip()) <= 200
            or not isinstance(now, datetime) or now.tzinfo is None
            or not isinstance(max_devices, int)
            or not 0 < max_devices <= _MAX_DEVICES
            or not isinstance(max_patches, int)
            or not 0 < max_patches <= _MAX_PATCHES):
        raise VulscanPatchEvidenceError("scoped site/limits/clock unavailable")

    discovery = read("endpoint.device.search", {
        "site": site_name.strip(), "completeness_requirement": "complete",
    })
    if not isinstance(discovery, Mapping) or discovery.get("status") != "succeeded":
        raise VulscanPatchEvidenceError("complete governed device discovery unavailable")
    evidence = discovery.get("evidence")
    if not isinstance(evidence, Mapping):
        raise VulscanPatchEvidenceError("device discovery evidence unavailable")
    matches = evidence.get("resource_matches")
    meta = evidence.get("search")
    if (evidence.get("discovery_complete") is not True
            or not isinstance(matches, list)
            or not isinstance(meta, Mapping)
            or meta.get("discovery_mode") != "authorized_account_collection"
            or meta.get("match_output_bounded") is not False
            or meta.get("incomplete_reason") not in (None, "")
            or not isinstance(evidence.get("match_count"), int)
            or evidence["match_count"] != len(matches)
            or not 0 < len(matches) <= max_devices):
        raise VulscanPatchEvidenceError("Datto site device discovery incomplete")
    try:
        pages = int(meta["provider_pages_examined"])
        account_total = int(meta["provider_total_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VulscanPatchEvidenceError("Datto device pagination proof missing") from exc
    if pages < 1 or pages > 50 or account_total < len(matches):
        raise VulscanPatchEvidenceError("Datto site device discovery pagination contradictory")

    unique: set[str] = set()
    for item in matches:
        if not isinstance(item, Mapping):
            raise VulscanPatchEvidenceError("Datto device discovery record malformed")
        uid = str(item.get("resource_id") or "")
        if (not _UID.fullmatch(uid) or uid in unique
                or str(item.get("site_id") or "") != site.site_uid
                or str(item.get("site") or "").casefold() != site_name.strip().casefold()):
            raise VulscanPatchEvidenceError("Datto device not uniquely scoped to site")
        unique.add(uid)

    collected: list[Mapping[str, Any]] = []
    scanned = 0
    for uid in sorted(unique):
        result = read("endpoint.patch.search", {
            "resource_id": uid, "completeness_requirement": "complete",
        })
        if not isinstance(result, Mapping) or result.get("status") != "succeeded":
            raise VulscanPatchEvidenceError("Datto endpoint patch read unavailable")
        proof = result.get("evidence")
        if not isinstance(proof, Mapping):
            raise VulscanPatchEvidenceError("Datto patch evidence missing")
        patches = proof.get("items")
        page = proof.get("pageDetails")
        if (proof.get("provider") != "datto_rmm"
                or proof.get("provider_capability") != "datto_rmm.device.patches.list"
                or proof.get("collection_key") != "patches"
                or proof.get("bounded") is not False
                or not isinstance(patches, list)
                or not isinstance(page, Mapping)
                or page.get("nextPageUrl") not in (None, "")):
            raise VulscanPatchEvidenceError("complete Datto device patch collection unavailable")
        try:
            total = int(page["totalCount"])
        except (KeyError, TypeError, ValueError) as exc:
            raise VulscanPatchEvidenceError("Datto device patch total missing") from exc
        if total != len(patches) or scanned + total > max_patches:
            raise VulscanPatchEvidenceError("Datto device patch pagination/budget incomplete")
        count_returned = proof.get("item_count_returned")
        if count_returned is not None and count_returned != len(patches):
            raise VulscanPatchEvidenceError("Datto device patch returned-count inconsistent")
        scanned += total
        for patch in patches:
            if not isinstance(patch, Mapping):
                raise VulscanPatchEvidenceError("Datto patch record malformed")
            if patch.get("deviceUid") not in (None, uid):
                raise VulscanPatchEvidenceError("patch was associated with another device")
            if (str(patch.get("installStatus") or "").strip().upper() == "NOT_APPROVED"
                    and _KB.fullmatch(str(patch.get("kbArticleId") or "").strip())):
                collected.append({**patch, "deviceUid": uid})

    return VerifiedDattoSitePatchCollection(
        site_uid=site.site_uid,
        client_id=site.client_id,
        patch_records=tuple(collected),
        scanned_devices=len(unique),
        scanned_patches=scanned,
        full_scope_verified=True,
        observed_at=now,
        source_reference=f"governed-datto-device-patches:{site.site_uid}",
    )
