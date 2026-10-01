from datetime import datetime, timedelta, timezone

from .deb_availability import (
    DebAvailabilityState,
    select_deb_asset,
)


NOW = datetime(2026, 9, 30, 17, 40, tzinfo=timezone.utc)


def test_single_online_asset_is_online():
    result = select_deb_asset(
        [
            {
                "id": "asset-new",
                "name": "PC-1",
                "status": "online",
                "lastSuccessfulBackupTimestamp": "2026-09-30T17:20:00Z",
            }
        ],
        hostname="PC-1",
        observed_at=NOW,
    )
    assert result.state is DebAvailabilityState.ONLINE
    assert result.selected_asset_id == "asset-new"


def test_single_offline_asset_is_offline():
    result = select_deb_asset(
        [
            {
                "id": "asset-1",
                "name": "PC-1",
                "status": "offline",
                "lastOnlineTimestamp": "2026-09-29T10:00:00Z",
            }
        ],
        hostname="PC-1",
        observed_at=NOW,
    )
    assert result.state is DebAvailabilityState.OFFLINE


def test_tus_51704_pattern_prefers_recent_online_asset_over_stale_duplicate():
    result = select_deb_asset(
        [
            {
                "id": "E0JKMFRFY",
                "name": "TUS-51704",
                "status": "online",
                "createdTimestamp": "2026-07-16T13:52:15Z",
                "lastSuccessfulBackupTimestamp": "2026-09-30T17:20:06Z",
            },
            {
                "id": "NUMJWHLJZ",
                "name": "TUS-51704",
                "status": "offline",
                "createdTimestamp": "2025-08-12T15:37:49Z",
                "lastOnlineTimestamp": "2026-07-06T22:24:51Z",
                "lastSuccessfulBackupTimestamp": "2026-07-06T20:36:44Z",
            },
        ],
        hostname="TUS-51704",
        observed_at=NOW,
    )
    assert result.state is DebAvailabilityState.ONLINE
    assert result.selected_asset_id == "E0JKMFRFY"
    assert result.exact_match_count == 2


def test_stale_online_duplicate_does_not_override_recent_offline_record():
    result = select_deb_asset(
        [
            {
                "id": "old-online",
                "name": "PC-1",
                "status": "online",
                "lastSuccessfulBackupTimestamp": "2026-09-20T10:00:00Z",
            },
            {
                "id": "recent-offline",
                "name": "PC-1",
                "status": "offline",
                "lastOnlineTimestamp": "2026-09-30T17:30:00Z",
            },
        ],
        hostname="PC-1",
        observed_at=NOW,
    )
    assert result.state is DebAvailabilityState.AMBIGUOUS


def test_multiple_current_online_records_are_ambiguous():
    result = select_deb_asset(
        [
            {
                "id": "a",
                "name": "PC-1",
                "status": "online",
                "lastSuccessfulBackupTimestamp": "2026-09-30T17:20:00Z",
            },
            {
                "id": "b",
                "name": "PC-1",
                "status": "online",
                "lastSuccessfulBackupTimestamp": "2026-09-30T17:25:00Z",
            },
        ],
        hostname="PC-1",
        observed_at=NOW,
    )
    assert result.state is DebAvailabilityState.AMBIGUOUS


def test_all_offline_duplicates_corroborate_offline_using_most_recent_record():
    result = select_deb_asset(
        [
            {
                "id": "older",
                "name": "PC-1",
                "status": "offline",
                "lastOnlineTimestamp": "2026-09-01T10:00:00Z",
            },
            {
                "id": "newer",
                "name": "PC-1",
                "status": "offline",
                "lastOnlineTimestamp": "2026-09-29T10:00:00Z",
            },
        ],
        hostname="PC-1",
        observed_at=NOW,
    )
    assert result.state is DebAvailabilityState.OFFLINE
    assert result.selected_asset_id == "newer"


def test_no_exact_asset_is_not_found():
    result = select_deb_asset(
        [{"id": "x", "name": "OTHER", "status": "online"}],
        hostname="PC-1",
        observed_at=NOW,
    )
    assert result.state is DebAvailabilityState.NOT_FOUND


def test_duplicate_online_freshness_is_bounded():
    result = select_deb_asset(
        [
            {
                "id": "online-old",
                "name": "PC-1",
                "status": "online",
                "lastSuccessfulBackupTimestamp": "2026-09-28T17:20:00Z",
            },
            {
                "id": "offline-older",
                "name": "PC-1",
                "status": "offline",
                "lastOnlineTimestamp": "2026-09-20T10:00:00Z",
            },
        ],
        hostname="PC-1",
        observed_at=NOW,
        duplicate_online_freshness=timedelta(hours=24),
    )
    assert result.state is DebAvailabilityState.AMBIGUOUS
