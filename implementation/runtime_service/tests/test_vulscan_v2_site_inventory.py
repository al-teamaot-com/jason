from jason_runtime.vulscan_governed_patch_source import VulscanPatchEvidenceError
from jason_runtime.vulscan_v2_site_inventory import (
    ApprovedDattoSiteInventory, ApprovedDattoSiteScope,
    collect_vulscan_v2_scoped_inventory,
)
import pytest

SITE = "17065ca1-dfdf-4c6b-95c7-8a8a5f5dc14a"
DEV = "274a6584-9d54-3e41-654f-046670799281"


def inventory(**kw):
    values = dict(
        sites=(ApprovedDattoSiteScope(SITE, "company-12", True),),
        full_scope_verified=True, source_reference="governed-authorized-site-map-v1",
    )
    values.update(kw)
    return ApprovedDattoSiteInventory(**values)


def reader(*, patch_records=None, site_override=None, policy_total=None, no_uid=False,
           truncated=False, unassigned=False):
    calls = []
    patch_records = patch_records if patch_records is not None else [
        {"deviceUid": DEV if not no_uid else "",
         "kbArticleId": "5127648", "installStatus": "NOT_APPROVED"},
        {"deviceUid": DEV, "kbArticleId": "", "installStatus": "NOT_APPROVED"},
    ]
    def read(capability, arguments):
        calls.append((capability, arguments))
        if capability == "management.site.patch.search":
            return {"status": "succeeded", "evidence": {
                "items": patch_records, "collection_key": "patches",
                "pageDetails": {
                    "totalCount": len(patch_records) + (1 if truncated else 0),
                    "nextPageUrl": None,
                }, "bounded": False}}
        if capability == "endpoint.device.read":
            return {"status": "succeeded", "evidence": {
                "record": {
                    "resource_id": DEV, "site_id": site_override or SITE,
                    "hostname": "PC-01",
                }}}
        if capability == "endpoint.patch.policy.search":
            items = [] if unassigned else [{"policyUid": "weekly-workstations"}]
            return {"status": "succeeded", "evidence": {
                "items": items, "collection_key": "policies",
                "pageDetails": {"totalCount": len(items) if policy_total is None else policy_total,
                                "nextPageUrl": None},
                "bounded": False}}
        raise AssertionError("unsupported capability")
    return read, calls


def test_real_site_scope_generates_one_exact_target_per_kb_policy_device():
    read, calls = reader()
    result = collect_vulscan_v2_scoped_inventory(
        site_inventory=inventory(), read=read)
    assert result.full_scope_verified is True
    assert len(result.targets) == 1
    t = result.targets[0]
    assert t.kb == "KB5127648"
    assert t.device_uid == DEV and t.hostname == "PC-01"
    assert t.policy_id == "weekly-workstations"
    assert t.client_id == "company-12"
    assert calls == [
        ("management.site.patch.search", {
            "resource_id": SITE, "completeness_requirement": "complete"}),
        ("endpoint.device.read", {"resource_id": DEV}),
        ("endpoint.patch.policy.search", {"resource_id": DEV}),
    ]


def test_empty_authoritative_site_patch_list_is_complete_and_safe():
    read, _ = reader(patch_records=[])
    result = collect_vulscan_v2_scoped_inventory(site_inventory=inventory(), read=read)
    assert result.full_scope_verified and result.targets == ()


@pytest.mark.parametrize("scenario,expected", [
    (dict(truncated=True), "pagination incomplete"),
    (dict(no_uid=True), "device identity"),
    (dict(site_override="wrong-site"), "verified managed site"),
    (dict(policy_total=2), "pagination incomplete"),
    (dict(unassigned=True), "assigned policy"),
])
def test_incomplete_or_cross_site_evidence_fails_closed(scenario, expected):
    read, _ = reader(**scenario)
    with pytest.raises(VulscanPatchEvidenceError, match=expected):
        collect_vulscan_v2_scoped_inventory(site_inventory=inventory(), read=read)


def test_unverified_client_site_mapping_is_never_promoted_to_evidence():
    read, calls = reader()
    for state in (
        inventory(full_scope_verified=False),
        inventory(sites=(ApprovedDattoSiteScope(SITE, "company-12", False),)),
        inventory(sites=(ApprovedDattoSiteScope(SITE, "company-12", True),
                         ApprovedDattoSiteScope(SITE, "company-99", True))),
    ):
        with pytest.raises(VulscanPatchEvidenceError):
            collect_vulscan_v2_scoped_inventory(site_inventory=state, read=read)
    assert calls == []


def test_multiple_policy_assignments_are_retained_as_references_not_causation():
    calls = []
    def read(capability, args):
        calls.append(capability)
        if capability == "management.site.patch.search":
            return {"status": "succeeded", "evidence": {
                "items": [{"deviceUid": DEV, "kbArticleId": "5127648",
                           "installStatus": "NOT_APPROVED"}],
                "pageDetails": {"totalCount": 1},
            }}
        if capability == "endpoint.device.read":
            return {"status": "succeeded", "evidence": {
                "record": {"resource_id": DEV, "hostname": "PC-01", "site_id": SITE}}}
        if capability == "endpoint.patch.policy.search":
            return {"status": "succeeded", "evidence": {
                "items": [{"policyUid": "policy-a"}, {"policyUid": "policy-b"}],
                "pageDetails": {"totalCount": 2},
            }}
        raise AssertionError("unrecognized")
    result = collect_vulscan_v2_scoped_inventory(site_inventory=inventory(), read=read)
    assert {x.policy_id for x in result.targets} == {"policy-a", "policy-b"}
    assert len(result.targets) == 2
