"""Acceptance fixtures for the governed VulScan patch-reader boundary."""
from datetime import date, datetime, timezone

import pytest

from jason_runtime.vulscan_governed_patch_source import (
    VerifiedPatchTarget, VulscanPatchEvidenceError,
    collect_governed_patch_observations,
)
from jason_runtime.vulscan_patch_approval_notification import MicrosoftKBMetadata

NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)


def target(**changes):
    values = dict(
        kb="KB5123456", client_id="company-12", policy_id="weekly-workstations",
        device_id="ci-10", device_uid="rmm-10", hostname="PC-10",
        identity_verified=True,
    )
    values.update(changes)
    return VerifiedPatchTarget(**values)


def release():
    return MicrosoftKBMetadata(
        kb="KB5123456", release_date=date(2026, 10, 13),
        title="Cumulative Update", summary="Verified summary",
        url="https://support.microsoft.com/help/5123456",
        source_checked_at=NOW, source_verified=True,
    )


def reader(*, status="NOT_APPROVED", reported_kb="5123456",
           uid="rmm-10", hostname="PC-10", failures=()):
    calls = []
    def read(capability, args):
        calls.append((capability, args))
        if capability in failures:
            raise PermissionError("read denied")
        if capability == "endpoint.device.read":
            return {"status": "succeeded", "evidence": {
                "record": {"resource_id": uid, "hostname": hostname}}}
        if capability == "endpoint.patch.policy.search":
            return {"status": "succeeded", "evidence": {"data": {"policies": [
                {"policyUid": "weekly-workstations"},
            ]}}}
        if capability == "endpoint.patch.search":
            return {"status": "succeeded", "evidence": {"data": {"patches": [
                {"kbArticleId": reported_kb, "installStatus": status},
            ]}}}
        assert False, "only two known governed reads permitted"
    return read, calls


def collect(ts, rd, **kw):
    return collect_governed_patch_observations(
        targets=ts, metadata_by_kb={"KB5123456": release()},
        read=rd, now=NOW, **kw)


def test_reads_exact_endpoint_and_kb_via_governed_capabilities():
    read, calls = reader()
    result = collect([target()], read)
    assert len(result) == 1
    assert result[0].approval_state == "NOT_APPROVED"
    assert result[0].release_date == date(2026, 10, 13)
    assert calls == [
        ("endpoint.device.read", {"resource_id": "rmm-10"}),
        ("endpoint.patch.policy.search", {"resource_id": "rmm-10"}),
        ("endpoint.patch.search", {"resource_id": "rmm-10", "kb": "KB5123456"}),
    ]


@pytest.mark.parametrize("bad", [
    dict(identity_verified=False),
    dict(client_id=""),
    dict(policy_id=""),
    dict(device_uid=""),
    dict(kb="not-a-kb"),
])
def test_identity_cannot_be_guessed(bad):
    read, calls = reader()
    with pytest.raises(VulscanPatchEvidenceError):
        collect([target(**bad)], read)
    assert calls == []


def test_different_readback_identity_fails_closed():
    for changes in (dict(uid="other"), dict(hostname="OTHER-PC")):
        read, _ = reader(**changes)
        with pytest.raises(VulscanPatchEvidenceError, match="UID/hostname"):
            collect([target()], read)


@pytest.mark.parametrize("changes", [
    dict(reported_kb="5129999"),
    dict(status=""),
    dict(status="PENDING"),
    dict(failures=("endpoint.patch.search",)),
    dict(failures=("endpoint.device.read",)),
])
def test_inexact_or_denied_patch_evidence_fails_closed(changes):
    read, _ = reader(**changes)
    with pytest.raises(VulscanPatchEvidenceError):
        collect([target()], read)


def test_contradictory_duplicate_device_cannot_mask_policy_or_hostname_mismatch():
    read, calls = reader()
    with pytest.raises(VulscanPatchEvidenceError, match="contradictory"):
        collect([target(), target(hostname="OTHER-PC")], read)
    assert calls == []


def test_duplicate_ticket_for_same_verified_device_is_not_double_counted():
    read, calls = reader()
    result = collect([target(), target()], read)
    assert len(result) == 1
    assert len(calls) == 3


def test_metadata_must_be_present_and_verified():
    read, calls = reader()
    with pytest.raises(VulscanPatchEvidenceError, match="Microsoft"):
        collect_governed_patch_observations(
            targets=[target()], metadata_by_kb={}, read=read, now=NOW)
    assert calls == []


def test_unassigned_policy_is_not_attributed_to_device():
    read, _ = reader()
    with pytest.raises(VulscanPatchEvidenceError, match="policy"):
        collect([target(policy_id="unassigned-policy")], read)


def test_denied_patch_policy_read_fails_without_patch_status_guess():
    read, calls = reader(failures=("endpoint.patch.policy.search",))
    with pytest.raises(VulscanPatchEvidenceError):
        collect([target()], read)
    assert all(cap != "endpoint.patch.search" for cap, _ in calls)


def test_actual_jason_governed_collection_envelope_shape():
    """Anonymized structure derived from a governed live endpoint.patch.search."""
    calls = []
    def live_read(capability, arguments):
        calls.append(capability)
        if capability == "endpoint.device.read":
            return {"status": "succeeded", "evidence": {
                "record": {"resource_id": "rmm-10", "hostname": "PC-10"}}}
        if capability == "endpoint.patch.policy.search":
            return {"status": "succeeded", "evidence": {
                "collection_key": "policies",
                "items": [{"policyUid": "weekly-workstations"}],
                "pageDetails": {"count": 1, "totalCount": 1, "nextPageUrl": None},
                "bounded": False,
            }}
        return {"status": "succeeded", "evidence": {
            "collection_key": "patches",
            "items": [{"kbArticleId": "5123456", "installStatus": "NOT_APPROVED"}],
            "item_count_returned": 1,
            "pageDetails": {"count": 34, "totalCount": 34, "nextPageUrl": None},
            "exact_selector_match": True, "ambiguous": False, "bounded": False,
        }}
    result = collect([target()], live_read)
    assert result[0].kb == "KB5123456"
    assert result[0].approval_state == "NOT_APPROVED"
    assert calls == ["endpoint.device.read", "endpoint.patch.policy.search", "endpoint.patch.search"]


def test_truncated_or_ambiguous_governed_collection_is_rejected():
    def make_read(*, policies_truncated=False, patch_ambiguous=False):
        def read(capability, arguments):
            if capability == "endpoint.device.read":
                return {"status": "succeeded", "evidence": {
                    "record": {"resource_id": "rmm-10", "hostname": "PC-10"}}}
            if capability == "endpoint.patch.policy.search":
                return {"status": "succeeded", "evidence": {
                    "items": [{"uid": "weekly-workstations"}],
                    "pageDetails": {"totalCount": 2 if policies_truncated else 1},
                    "bounded": False,
                }}
            return {"status": "succeeded", "evidence": {
                "items": [{"kbArticleId": "5123456", "installStatus": "NOT_APPROVED"}],
                "exact_selector_match": not patch_ambiguous,
                "ambiguous": patch_ambiguous,
            }}
        return read
    with pytest.raises(VulscanPatchEvidenceError, match="incomplete"):
        collect([target()], make_read(policies_truncated=True))
    with pytest.raises(VulscanPatchEvidenceError, match="unambiguous"):
        collect([target()], make_read(patch_ambiguous=True))
