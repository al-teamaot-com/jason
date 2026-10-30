"""VulScan V2 native Datto read-only endpoint acceptance.

The requests are prepared by Jason's existing connector; no live Datto calls
or modifications occur in these tests.
"""
from datetime import datetime, timezone

import pytest

from connectors.datto_rmm.connector import DattoRmmConnector
from connectors.datto_rmm.capability_manifest import build_datto_rmm_manifest
from orchestrator.resource_capability_catalog import (
    DATTO_RMM_PROVIDER, ENDPOINT_PATCH_POLICY_SEARCH, MANAGEMENT_SITE_PATCH_SEARCH,
    datto_rmm_endpoint_provider, endpoint_patch_policy_search,
    management_site_patch_search,
)


def test_provider_routes_exact_documented_read_only_endpoints():
    assert DattoRmmConnector._resolve_operation(
        "datto_rmm.device.patch_policies.list", {"resource_id": "device-123"}
    ) == ("/api/v2/device/device-123/policies/patch-management", {"page": 0, "max": 250})
    assert DattoRmmConnector._resolve_operation(
        "datto_rmm.site.patches.list", {"site_uid": "site-789"}
    ) == ("/api/v2/site/site-789/patches", {"page": 0, "max": 250})
    assert {
        "datto_rmm.device.patch_policies.list", "datto_rmm.site.patches.list",
    } <= DattoRmmConnector.capabilities


@pytest.mark.parametrize("bad", ["", "../account", "a/b", "test?x=1", "foo%2Fbar", "bad#fragment"])
def test_unverified_uid_cannot_escape_read_resource_path(bad):
    for capability, selector in (
        ("datto_rmm.device.patch_policies.list", "device_uid"),
        ("datto_rmm.site.patches.list", "site_uid"),
    ):
        with pytest.raises(ValueError):
            DattoRmmConnector._resolve_operation(capability, {selector: bad})


def test_site_page_size_is_bounded_and_provider_read_is_scoped():
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.site.patches.list", {"site_uid": "site-1", "page": 4, "max": 5000})
    assert path == "/api/v2/site/site-1/patches"
    assert params == {"page": 4, "max": 250}


def test_broker_manifest_exposes_read_only_same_resource_operations():
    manifest = build_datto_rmm_manifest()
    endpoint = next(x for x in manifest.resources if x.resource_type == "endpoint")
    site = next(x for x in manifest.resources if x.resource_type == "site")
    endpoint_operation = next(
        x for x in endpoint.operations if x.capability_name == ENDPOINT_PATCH_POLICY_SEARCH)
    site_operation = next(
        x for x in site.operations if x.capability_name == MANAGEMENT_SITE_PATCH_SEARCH)
    assert endpoint_operation.read_only is True
    assert site_operation.read_only is True


def test_canonical_policy_and_site_reads_are_low_risk_observe_only():
    now = datetime(2026, 10, 30, tzinfo=timezone.utc)
    provider = datto_rmm_endpoint_provider(now)
    assert provider.provider_id == DATTO_RMM_PROVIDER
    assert {ENDPOINT_PATCH_POLICY_SEARCH, MANAGEMENT_SITE_PATCH_SEARCH} <= provider.capabilities
    assert endpoint_patch_policy_search(now).capability_name == ENDPOINT_PATCH_POLICY_SEARCH
    assert management_site_patch_search(now).capability_name == MANAGEMENT_SITE_PATCH_SEARCH


def test_assigned_policy_list_and_items_normalize_into_bounded_record():
    raw = [{"policyUid": "weekly-workstations"}]
    assert DattoRmmConnector._normalize_result(
        "datto_rmm.device.patch_policies.list", raw) == {"policies": raw}
    assert DattoRmmConnector._normalize_result(
        "datto_rmm.device.patch_policies.list", {"items": raw, "pageDetails": {"totalCount": 1}}) == {
            "policies": raw, "pageDetails": {"totalCount": 1}}
    with pytest.raises(ValueError):
        DattoRmmConnector._normalize_result("datto_rmm.device.patch_policies.list", {})


def test_patch_policy_pagination_is_bounded_without_silent_truncation():
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.patch_policies.list",
        {"device_uid": "dev-1", "page": 3, "max": 5000})
    assert path == "/api/v2/device/dev-1/policies/patch-management"
    assert params == {"page": 3, "max": 250}
    assert DattoRmmConnector.adaptive_collection_keys[
        "datto_rmm.device.patch_policies.list"] == "policies"
