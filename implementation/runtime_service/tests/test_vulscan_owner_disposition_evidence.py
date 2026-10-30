from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from jason_runtime.vulscan_owner_disposition_evidence import (
    VerifiedPatchReviewDisposition, VulscanReviewDispositionUnavailable,
    verify_patch_review_disposition,
)

NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)


def record(**changes):
    values = dict(
        kb="KB5127648", client_id="company-12",
        policy_id="weekly", device_uid="datto-device-123",
        disposition="review_pending", checked_at=NOW,
        source_reference="governed-durable-owner-review-read-123",
        full_scope_verified=True,
    )
    values.update(changes)
    return VerifiedPatchReviewDisposition(**values)


def verify(result):
    return verify_patch_review_disposition(
        result, kb="KB5127648", client_id="company-12",
        policy_id="weekly", device_uid="datto-device-123", now=NOW,
    )


@pytest.mark.parametrize("state", ["review_pending", "deferred", "declined", "superseded"])
def test_exact_full_scope_signed_review_states(state):
    assert verify(record(disposition=state)).disposition == state


@pytest.mark.parametrize("change", [
    {"kb": "KB5129999"}, {"client_id": "another-client"},
    {"policy_id": "unrelated-policy"}, {"device_uid": "different-device"},
])
def test_cross_scope_reuse_fails_closed(change):
    with pytest.raises(VulscanReviewDispositionUnavailable, match="identity"):
        verify(record(**change))


@pytest.mark.parametrize("change", [
    {"full_scope_verified": False}, {"source_reference": ""},
    {"source_reference": "x" * 251}, {"disposition": "unknown"},
    {"disposition": "approved"}, {"disposition": "missing"},
])
def test_unknown_or_incomplete_scope_is_never_implicit_no_deferral(change):
    with pytest.raises(VulscanReviewDispositionUnavailable, match="coverage"):
        verify(record(**change))


def test_no_record_is_not_evidence_of_no_owner_deferral():
    with pytest.raises(VulscanReviewDispositionUnavailable, match="unavailable"):
        verify(None)


@pytest.mark.parametrize("offset", [-timedelta(minutes=16), timedelta(minutes=1)])
def test_stale_or_future_decision_is_not_authoritative(offset):
    with pytest.raises(VulscanReviewDispositionUnavailable, match="stale"):
        verify(record(checked_at=NOW + offset))


def test_unaware_decision_timestamp_is_rejected():
    with pytest.raises(VulscanReviewDispositionUnavailable, match="clock"):
        verify(record(checked_at=NOW.replace(tzinfo=None)))
