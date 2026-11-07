"""Proof that assigned patch policies are not inferred to cause device status."""
from datetime import datetime, timedelta, timezone
import pytest

from jason_runtime.vulscan_policy_kb_attribution import (
    VerifiedPolicyKBAttribution, PolicyKBAttributionUnavailable,
    verified_unapproved_policy_ids,
)

NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)
POLICIES = {"policy-a", "policy-b"}


def evidence(*, states=(("policy-a", "NOT_APPROVED"),
                        ("policy-b", "NOT_APPLICABLE")), **changes):
    values = dict(
        kb="KB5127648", client_id="company-a", site_uid="site-a",
        device_uid="device-a", policy_states=states,
        source_reference="governed-complete-per-KB-policy-decision",
        observed_at=NOW, full_scope_verified=True,
    )
    values.update(changes)
    return VerifiedPolicyKBAttribution(**values)


def verify(record, *, assigned=POLICIES):
    return verified_unapproved_policy_ids(
        record, kb="KB5127648", client_id="company-a",
        site_uid="site-a", device_uid="device-a",
        assigned_policy_ids=assigned, now=NOW,
    )


def test_only_proven_disapproving_policy_selected():
    assert verify(evidence()) == ("policy-a",)


@pytest.mark.parametrize("overrides", [
    {"kb": "KB5127650"}, {"client_id": "company-b"},
    {"site_uid": "site-b"}, {"device_uid": "device-b"},
])
def test_cross_client_site_or_kb_attestation_denied(overrides):
    with pytest.raises(PolicyKBAttributionUnavailable, match="identity"):
        verify(evidence(**overrides))


@pytest.mark.parametrize("overrides", [
    {"full_scope_verified": False},
    {"source_reference": ""},
    {"source_reference": "x" * 300},
    {"observed_at": NOW - timedelta(minutes=16)},
    {"observed_at": NOW + timedelta(seconds=1)},
    {"observed_at": NOW.replace(tzinfo=None)},
])
def test_partial_or_stale_source_rejected(overrides):
    with pytest.raises(PolicyKBAttributionUnavailable):
        verify(evidence(**overrides))


@pytest.mark.parametrize("states", [
    (("policy-a", "NOT_APPROVED"),),  # missing policy-b
    (("policy-a", "NOT_APPROVED"), ("policy-a", "NOT_APPROVED")),
    (("policy-a", "NOT_APPROVED"), ("policy-z", "NOT_APPLICABLE")),
    (("policy-a", "UNKNOWN"), ("policy-b", "NOT_APPLICABLE")),
    (("policy-a", "INSTALLED"), ("policy-b", "NOT_APPLICABLE")),
    (("policy-a", "APPROVED_PENDING"), ("policy-b", "NOT_APPLICABLE")),
])
def test_unverified_incomplete_or_non_causing_attribution_is_blocked(states):
    with pytest.raises(PolicyKBAttributionUnavailable):
        verify(evidence(states=states))


def test_no_provenance_cannot_be_mistaken_for_not_approved():
    with pytest.raises(PolicyKBAttributionUnavailable, match="missing"):
        verify(None)


def test_two_disapproving_policies_may_be_reported_only_if_both_proven():
    assert verify(evidence(states=(
        ("policy-a", "NOT_APPROVED"),
        ("policy-b", "NOT_APPROVED"),
    ))) == ("policy-a", "policy-b")
