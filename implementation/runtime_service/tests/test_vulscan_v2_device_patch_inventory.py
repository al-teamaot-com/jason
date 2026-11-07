"""Fail-closed source-only VulScan site aggregation over active governed reads."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from jason_runtime.vulscan_governed_patch_source import VulscanPatchEvidenceError
from jason_runtime.vulscan_policy_kb_attribution import VerifiedPolicyKBAttribution
from jason_runtime.vulscan_v2_device_patch_inventory import (
    collect_governed_site_patches_from_devices,
)
from jason_runtime.vulscan_v2_site_inventory import (
    ApprovedDattoSiteInventory, ApprovedDattoSiteScope,
    collect_vulscan_v2_scoped_inventory,
)

NOW = datetime(2026, 10, 31, 10, tzinfo=timezone.utc)
SITE = "site-verified-12"
CLIENT = "company-12"
NAME = "Verified Test Site"
D1, D2 = "device-12", "device-13"
SCOPE = ApprovedDattoSiteScope(SITE, CLIENT, True)


def discovery(*, devices=(D1, D2), **updates):
    matches = [
        {"resource_id": uid, "site_id": SITE, "site": NAME,
         "hostname": "PC-" + uid}
        for uid in devices
    ]
    evidence = {
        "resource_matches": matches,
        "match_count": len(matches),
        "discovery_complete": True,
        "search": {
            "discovery_mode": "authorized_account_collection",
            "match_output_bounded": False,
            "incomplete_reason": None,
            "provider_pages_examined": 5,
            "provider_total_count": 752,
        },
    }
    evidence.update(updates)
    return {"status": "succeeded", "evidence": evidence}


def patches(uid, **updates):
    values = [
        {"patchId": "patch-1", "kbArticleId": "5127648",
         "installStatus": "NOT_APPROVED", "manualOverride": False},
        {"patchId": "patch-2", "kbArticleId": "5128888",
         "installStatus": "INSTALLED", "manualOverride": False},
        {"patchId": "firmware", "kbArticleId": "",
         "installStatus": "NOT_APPROVED"},
    ]
    evidence = {
        "provider": "datto_rmm",
        "provider_capability": "datto_rmm.device.patches.list",
        "collection_key": "patches", "items": values,
        "item_count_returned": 3,
        "bounded": False,
        "pageDetails": {"count": 3, "totalCount": 3, "nextPageUrl": None},
    }
    evidence.update(updates)
    return {"status": "succeeded", "evidence": evidence}


def reader(*, device_response=None, patch_overrides=None):
    calls = []
    def read(cap, args):
        calls.append((cap, args))
        if cap == "endpoint.device.search":
            return device_response if device_response is not None else discovery()
        if cap == "endpoint.patch.search":
            return patches(args["resource_id"], **(patch_overrides or {}))
        raise AssertionError("source-only reader was invoked outside approved scope")
    return read, calls


def collect(*, read=None, **kw):
    if read is None:
        read, _ = reader()
    return collect_governed_site_patches_from_devices(
        site=SCOPE, site_name=NAME, read=read, now=NOW, **kw,
    )


def test_two_complete_devices_produce_only_true_not_approved_windows_kb():
    read, calls = reader()
    proof = collect(read=read)
    assert proof.site_uid == SITE and proof.client_id == CLIENT
    assert proof.full_scope_verified
    assert proof.scanned_devices == 2 and proof.scanned_patches == 6
    assert len(proof.patch_records) == 2
    assert {x["deviceUid"] for x in proof.patch_records} == {D1, D2}
    assert {x["kbArticleId"] for x in proof.patch_records} == {"5127648"}
    assert calls[0] == (
        "endpoint.device.search",
        {"site": NAME, "completeness_requirement": "complete"},
    )
    assert len(calls) == 3
    assert all(c == "endpoint.patch.search" for c, _ in calls[1:])
    assert all(a["completeness_requirement"] == "complete" for _, a in calls)


@pytest.mark.parametrize("variation", [
    {"discovery_complete": False},
    {"match_count": 3},
    {"resource_matches": []},
    {"resource_matches": [{"resource_id": D1, "site_id": "other", "site": NAME}]},
    {"resource_matches": [{"resource_id": D1, "site_id": SITE, "site": NAME}] * 2},
    {"search": {"discovery_mode": "authorized_account_collection",
                "match_output_bounded": True}},
    {"search": {"discovery_mode": "exact_hostname_lookup",
                "match_output_bounded": False}},
])
def test_invalid_or_partial_discovery_rejected_before_patch_calls(variation):
    read, calls = reader(device_response=discovery(**variation))
    with pytest.raises(VulscanPatchEvidenceError):
        collect(read=read)
    assert [x for x, _ in calls] == ["endpoint.device.search"]


@pytest.mark.parametrize("bad_evidence", [
    {"provider": "unknown"},
    {"provider_capability": "datto_rmm.site.patches.list"},
    {"collection_key": "wrong"},
    {"bounded": True},
    {"item_count_returned": 2},
    {"pageDetails": {"totalCount": 3, "nextPageUrl": "unread-page"}},
    {"pageDetails": {"totalCount": 4, "nextPageUrl": None}},
    {"items": [{"kbArticleId": "5127648", "deviceUid": "other",
                "installStatus": "NOT_APPROVED"}]},
    {"items": [None]},
])
def test_incomplete_or_cross_device_patch_page_fails(bad_evidence):
    read, _ = reader(patch_overrides=bad_evidence)
    with pytest.raises(VulscanPatchEvidenceError):
        collect(read=read)


def test_bounded_global_scan_can_never_truncate_and_claim_complete():
    read, _ = reader()
    with pytest.raises(VulscanPatchEvidenceError, match="discovery incomplete"):
        collect(read=read, max_devices=1)
    with pytest.raises(VulscanPatchEvidenceError, match="budget incomplete"):
        collect(read=read, max_patches=5)


def test_existing_v2_inventory_can_explicitly_use_governed_device_source():
    read, calls = reader()
    def rest(cap, args):
        if cap == "endpoint.device.read":
            uid = args["resource_id"]
            assert uid in (D1, D2)
            return {"status": "succeeded", "evidence": {"record": {
                "resource_id": uid, "site_id": SITE, "hostname": "PC-" + uid,
            }}}
        if cap == "endpoint.patch.policy.search":
            assert args["resource_id"] in (D1, D2)
            return {"status": "succeeded", "evidence": {
                "items": [{"policyUid": "weekly"}],
                "collection_key": "policies",
                "bounded": False,
                "pageDetails": {"totalCount": 1, "nextPageUrl": None},
            }}
        raise AssertionError("new site API was incorrectly called")

    def attribution(site, client, device, kb):
        return VerifiedPolicyKBAttribution(
            kb=kb, client_id=client, site_uid=site, device_uid=device,
            policy_states=(("weekly", "NOT_APPROVED"),),
            source_reference="fixture-current-policy-KB-evidence",
            full_scope_verified=True, observed_at=NOW,
        )

    inventory = collect_vulscan_v2_scoped_inventory(
        site_inventory=ApprovedDattoSiteInventory(
            sites=(SCOPE,), full_scope_verified=True,
            source_reference="verified-same-client-site",
        ),
        read=rest, now=NOW, policy_attribution_read=attribution,
        verified_device_site_patch_read=lambda scope:
            collect_governed_site_patches_from_devices(
                site=scope, site_name=NAME, read=read, now=NOW,
            ),
    )
    assert inventory.full_scope_verified and len(inventory.targets) == 2
    assert {x.device_uid for x in inventory.targets} == {D1, D2}
    assert all(x.policy_id == "weekly" for x in inventory.targets)
    assert all(x.site_uid == SITE for x in inventory.targets)
    assert len(calls) == 3


@pytest.mark.parametrize("bad", [
    {"full_scope_verified": False},
    {"site_uid": "other-site"},
    {"client_id": "another-client"},
    {"observed_at": NOW - timedelta(minutes=16)},
    {"source_reference": ""},
    {"scanned_devices": 0},
    {"scanned_patches": 0},
])
def test_alternate_site_proof_must_be_fresh_complete_and_scoped(bad):
    proof = replace(collect(), **bad)
    def forbidden(cap, args):
        raise AssertionError("invalid proof may not trigger downstream reads")
    with pytest.raises(VulscanPatchEvidenceError):
        collect_vulscan_v2_scoped_inventory(
            site_inventory=ApprovedDattoSiteInventory(
                sites=(SCOPE,), full_scope_verified=True,
                source_reference="verified-same-client-site",
            ),
            read=forbidden, now=NOW,
            policy_attribution_read=lambda *a: None,
            verified_device_site_patch_read=lambda _: proof,
        )
