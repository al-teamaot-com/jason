"""Regression tests for governed Datto RMM intentional patch decisions.

No Datto credentials, provider mutation, Teams send or endpoint changes.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest

from jason_runtime.vulscan_datto_review_evidence import (
    DattoManualReviewUnavailable, DattoRmmPatchReviewReader,
    VerifiedDattoPolicyManualReview, verify_datto_manual_policy_review,
)
from jason_runtime.vulscan_governed_patch_source import VerifiedPatchTarget

NOW = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)
KB = "KB5127648"
SITE = "site-12"
DEVICE = "device-12"


def target(**kwargs):
    defaults = dict(
        kb=KB, client_id="company-12", policy_id="weekly",
        device_id=DEVICE, device_uid=DEVICE, hostname="PC-12",
        identity_verified=True, site_uid=SITE,
        policy_kb_attribution_verified=True,
        policy_kb_attribution_reference="verified-datto-KB-policy-causation",
        policy_kb_attribution_checked_at=NOW,
    )
    defaults.update(kwargs)
    return VerifiedPatchTarget(**defaults)


def policy_review(t, **kwargs):
    defaults = dict(
        kb=t.kb, client_id=t.client_id, site_uid=t.site_uid,
        device_uid=t.device_uid, policy_uid=t.policy_id,
        decision="no_manual_denial", manual_table_complete=True,
        assigned_policy_verified=True,
        checked_at=NOW, full_scope_verified=True,
        source_reference="governed-datto-complete-policy-manual-approval-table",
        provider="datto_rmm",
    )
    defaults.update(kwargs)
    return VerifiedDattoPolicyManualReview(**defaults)


def response(*, manual=False, state="NOT_APPROVED", **evidence_overrides):
    evidence = {
        "items": [{
            "kbArticleId": KB[2:], "installStatus": state,
            "manualOverride": manual,
        }],
        "collection_key": "patches",
        "pageDetails": {"count": 1, "totalCount": 1, "nextPageUrl": None},
        "bounded": False,
        "exact_selector_match": True, "ambiguous": False,
    }
    evidence.update(evidence_overrides)
    return {"status": "succeeded", "evidence": evidence}


def make_reader(*, patch=None, decision="no_manual_denial", policy=None):
    calls = []
    def read(capability, arguments):
        calls.append((capability, arguments))
        return patch if patch is not None else response()

    def policy_read(t):
        calls.append(("datto_manual_policy_table", t.policy_id))
        return policy(t) if policy is not None else policy_review(t, decision=decision)

    return DattoRmmPatchReviewReader(read, policy_read, now=lambda: NOW), calls


def test_device_level_do_not_approve_supersedes_policy_pending_without_fake_owner():
    reader, calls = make_reader(patch=response(manual=True))
    record = reader(target())
    assert record.disposition == "declined"
    assert record.full_scope_verified is True
    assert record.source_reference.startswith("datto_rmm:governed:")
    assert len(calls) == 1
    assert calls[0][0] == "endpoint.patch.search"
    assert calls[0][1] == {
        "resource_id": DEVICE, "kb": KB, "completeness_requirement": "complete",
    }


def test_complete_manual_policy_denial_suppresses_notification():
    reader, calls = make_reader(decision="manual_not_approved")
    assert reader(target()).disposition == "declined"
    assert len(calls) == 2


def test_only_complete_manual_table_can_attest_no_explicit_datto_denial():
    reader, calls = make_reader()
    proof = reader(target())
    assert proof.disposition == "review_pending"
    assert proof.full_scope_verified
    assert len(calls) == 2


def test_effective_not_approved_without_manual_table_is_unknown_not_pending():
    reader, calls = make_reader(policy=lambda t: None)
    with pytest.raises(DattoManualReviewUnavailable, match="complete governed"):
        reader(target())
    assert len(calls) == 2


@pytest.mark.parametrize("field", [
    {"client_id": "another-client"}, {"site_uid": "another-site"},
    {"device_uid": "another-device"}, {"policy_uid": "another-policy"},
    {"kb": "KB5129999"}, {"provider": "unknown"},
])
def test_cross_tenant_policy_or_kb_disposition_is_not_reusable(field):
    reader, _ = make_reader(policy=lambda t: policy_review(t, **field))
    with pytest.raises(DattoManualReviewUnavailable, match="complete governed"):
        reader(target())


@pytest.mark.parametrize("field", [
    {"manual_table_complete": False},
    {"assigned_policy_verified": False},
    {"full_scope_verified": False},
    {"source_reference": ""},
    {"decision": "NOT_APPROVED"},
    {"decision": "deferred"},
    {"checked_at": NOW - timedelta(minutes=16)},
    {"checked_at": NOW + timedelta(seconds=1)},
    {"checked_at": NOW.replace(tzinfo=None)},
])
def test_partial_stale_or_inferred_policy_decision_fails_closed(field):
    reader, _ = make_reader(policy=lambda t: policy_review(t, **field))
    with pytest.raises(DattoManualReviewUnavailable):
        reader(target())


@pytest.mark.parametrize("override", ["false", 0, 1, None, "true"])
def test_missing_or_malformed_device_override_is_not_negative_attestation(override):
    reader, _ = make_reader(patch=response(manual=override))
    with pytest.raises(DattoManualReviewUnavailable, match="manual override"):
        reader(target())


@pytest.mark.parametrize("bad_patch", [
    response(state="INSTALLED"),
    response(state="APPROVED_PENDING"),
    response(manual=True, state="APPROVED_PENDING"),
    response(pageDetails={"count": 1, "totalCount": 1, "nextPageUrl": "another-page"}),
    response(bounded=True),
    response(exact_selector_match=False),
    response(ambiguous=True),
    response(items=[{"kbArticleId": "5129999", "installStatus": "NOT_APPROVED", "manualOverride": False}]),
    response(items=[]),
    response(items=[{"kbArticleId": KB[2:], "installStatus": "NOT_APPROVED", "manualOverride": False}] * 2),
])
def test_unverifiable_endpoint_patch_never_produces_review_disposition(bad_patch):
    reader, _ = make_reader(patch=bad_patch)
    with pytest.raises(DattoManualReviewUnavailable):
        reader(target())


@pytest.mark.parametrize("field", [
    {"identity_verified": False},
    {"policy_kb_attribution_verified": False},
    {"site_uid": ""},
    {"site_uid": "other/site"},
])
def test_unverified_target_is_blocked_before_provider_read(field):
    reader, calls = make_reader()
    with pytest.raises(DattoManualReviewUnavailable, match="identity"):
        reader(target(**field))
    assert calls == []


def test_competing_manual_evidence_sources_cannot_be_silently_combined():
    proof = policy_review(target())
    with pytest.raises(DattoManualReviewUnavailable, match="scope mismatch"):
        verify_datto_manual_policy_review(
            replace(proof, site_uid="another-site"), target=target(), now=NOW,
        )
