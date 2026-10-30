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
        if capability == "endpoint.patch_policy.search":
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
        ("endpoint.patch_policy.search", {"resource_id": "rmm-10"}),
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
    read, calls = reader(failures=("endpoint.patch_policy.search",))
    with pytest.raises(VulscanPatchEvidenceError):
        collect([target()], read)
    assert all(cap != "endpoint.patch.search" for cap, _ in calls)
