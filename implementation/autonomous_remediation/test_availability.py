from datetime import datetime, timedelta, timezone

import pytest

from .availability import (
    AvailabilityObservation,
    AvailabilityState,
    OfflineVerificationPolicy,
    PeerProbeResult,
    assess_endpoint_availability,
)


NOW = datetime(2026, 9, 21, 17, 0, tzinfo=timezone.utc)
POLICY = OfflineVerificationPolicy(
    peer_verify_after=timedelta(hours=2),
    retry_after=timedelta(hours=1),
)


def test_online_needs_no_recheck():
    r = assess_endpoint_availability(
        AvailabilityObservation("pc-1", NOW, True, NOW - timedelta(minutes=1)), POLICY
    )
    assert r.state == AvailabilityState.ONLINE
    assert not r.recheck_required


def test_recent_offline_waits_until_threshold():
    last_seen = NOW - timedelta(minutes=30)
    r = assess_endpoint_availability(
        AvailabilityObservation("pc-1", NOW, False, last_seen), POLICY
    )
    assert r.state == AvailabilityState.RECENTLY_OFFLINE
    assert r.next_recheck_at == last_seen + timedelta(hours=2)


def test_stale_offline_requests_peer_verification():
    r = assess_endpoint_availability(
        AvailabilityObservation(
            "pc-1", NOW, False, NOW - timedelta(hours=3),
            same_site_peer_available=True
        ),
        POLICY,
    )
    assert r.state == AvailabilityState.PEER_VERIFICATION_DUE
    assert r.peer_verification_required


def test_missing_peer_rechecks_instead_of_blocking():
    r = assess_endpoint_availability(
        AvailabilityObservation(
            "pc-1", NOW, False, NOW - timedelta(hours=3),
            same_site_peer_available=False
        ),
        POLICY,
    )
    assert r.state == AvailabilityState.PEER_UNAVAILABLE
    assert r.recheck_required
    assert r.next_recheck_at == NOW + timedelta(hours=1)


def test_peer_ping_success_flags_drmm_path_issue():
    probe = PeerProbeResult(
        "peer-1", NOW, hostname_resolved=True, resolved_ip="192.0.2.50",
        hostname_ping_succeeded=True, ip_ping_succeeded=True
    )
    r = assess_endpoint_availability(
        AvailabilityObservation(
            device_id="pc-1", observed_at=NOW, drmm_online=False,
            last_seen_at=NOW - timedelta(hours=3), hostname="pc-1",
            last_known_ip="192.0.2.50", same_site_peer_available=True,
            peer_probe=probe
        ),
        POLICY,
    )
    assert r.state == AvailabilityState.REACHABLE_OUTSIDE_DRMM
    assert r.drmm_agent_issue_suspected
    assert not r.recheck_required


def test_failed_pings_are_not_definitive():
    probe = PeerProbeResult(
        "peer-1", NOW, hostname_resolved=True, resolved_ip="192.0.2.50",
        hostname_ping_succeeded=False, ip_ping_succeeded=False
    )
    r = assess_endpoint_availability(
        AvailabilityObservation(
            device_id="pc-1", observed_at=NOW, drmm_online=False,
            last_seen_at=NOW - timedelta(hours=3), hostname="pc-1",
            last_known_ip="192.0.2.50", same_site_peer_available=True,
            peer_probe=probe
        ),
        POLICY,
    )
    assert r.state == AvailabilityState.OFFLINE_LIKELY
    assert r.recheck_required


def test_unknown_last_seen_does_not_wait_forever():
    r = assess_endpoint_availability(
        AvailabilityObservation(
            "pc-1", NOW, False, None, same_site_peer_available=True
        ),
        POLICY,
    )
    assert r.state == AvailabilityState.PEER_VERIFICATION_DUE


def test_persisted_payload_contains_resume_fields():
    r = assess_endpoint_availability(
        AvailabilityObservation(
            "pc-1", NOW, False, NOW - timedelta(minutes=30)
        ),
        POLICY,
    )
    payload = r.persisted_payload()
    assert payload["state"] == "recently_offline"
    assert payload["recheck_required"] is True
    assert payload["next_recheck_at"] is not None


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        AvailabilityObservation(
            "pc-1", datetime(2026, 9, 21, 13, 0), False, None
        )
