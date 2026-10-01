"""Shared Datto Endpoint Backup availability selection for Jason."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


class DebAvailabilityState(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


_OFFLINE_STATES = frozenset({"offline", "inactive", "disconnected"})


@dataclass(frozen=True, slots=True)
class DebAssetSelection:
    state: DebAvailabilityState
    hostname: str
    exact_match_count: int
    asset: Mapping[str, Any] | None
    selected_asset_id: str | None
    selected_status: str | None
    activity_at: datetime | None
    reason: str

    @property
    def online(self) -> bool:
        return self.state is DebAvailabilityState.ONLINE

    @property
    def offline(self) -> bool:
        return self.state is DebAvailabilityState.OFFLINE


def parse_deb_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def deb_asset_activity_at(asset: Mapping[str, Any]) -> datetime | None:
    values = [
        parse_deb_timestamp(asset.get("lastOnlineTimestamp")),
        parse_deb_timestamp(asset.get("lastSuccessfulBackupTimestamp")),
        parse_deb_timestamp(asset.get("createdTimestamp")),
    ]
    present = [value for value in values if value is not None]
    return max(present) if present else None


def select_deb_asset(
    items: Sequence[Any],
    *,
    hostname: str,
    observed_at: datetime,
    duplicate_online_freshness: timedelta = timedelta(hours=24),
) -> DebAssetSelection:
    """Resolve exact same-name DEB assets without trusting stale duplicates.

    A single exact match is accepted according to its current provider status.
    With duplicate exact-name records, one online record may win only when it has
    recent activity and every other exact record is non-online and older. This
    handles normal replacement/reinstall history while failing closed on genuine
    current ambiguity.
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    target = str(hostname or "").strip()
    if not target:
        raise ValueError("hostname must be non-empty")

    exact = [
        item
        for item in items
        if isinstance(item, Mapping)
        and str(item.get("name") or "").strip().casefold() == target.casefold()
    ]
    if not exact:
        return DebAssetSelection(
            DebAvailabilityState.NOT_FOUND,
            target,
            0,
            None,
            None,
            None,
            None,
            "No exact same-name DEB asset was found.",
        )

    def status(asset: Mapping[str, Any]) -> str:
        return str(asset.get("status") or "").strip().casefold()

    def asset_id(asset: Mapping[str, Any]) -> str | None:
        value = str(asset.get("id") or asset.get("assetId") or "").strip()
        return value or None

    def selected(
        state: DebAvailabilityState,
        asset: Mapping[str, Any],
        reason: str,
    ) -> DebAssetSelection:
        return DebAssetSelection(
            state=state,
            hostname=target,
            exact_match_count=len(exact),
            asset=asset,
            selected_asset_id=asset_id(asset),
            selected_status=status(asset) or None,
            activity_at=deb_asset_activity_at(asset),
            reason=reason,
        )

    if len(exact) == 1:
        asset = exact[0]
        current = status(asset)
        if current == "online":
            return selected(
                DebAvailabilityState.ONLINE,
                asset,
                "The exact DEB asset currently reports online.",
            )
        if current in _OFFLINE_STATES:
            return selected(
                DebAvailabilityState.OFFLINE,
                asset,
                "The exact DEB asset currently reports offline.",
            )
        return selected(
            DebAvailabilityState.UNKNOWN,
            asset,
            "The exact DEB asset has an unrecognized availability status.",
        )

    online = [asset for asset in exact if status(asset) == "online"]
    non_online = [asset for asset in exact if status(asset) != "online"]

    if len(online) == 1 and all(status(asset) in _OFFLINE_STATES for asset in non_online):
        current = online[0]
        current_activity = deb_asset_activity_at(current)
        other_activity = [
            deb_asset_activity_at(asset)
            for asset in non_online
            if deb_asset_activity_at(asset) is not None
        ]
        cutoff = observed_at.astimezone(timezone.utc) - duplicate_online_freshness
        newer_than_others = (
            current_activity is not None
            and all(current_activity > value for value in other_activity)
        )
        if (
            current_activity is not None
            and current_activity >= cutoff
            and newer_than_others
        ):
            return selected(
                DebAvailabilityState.ONLINE,
                current,
                "One exact DEB asset is online with recent activity and all duplicate "
                "records are older offline history.",
            )

    if not online and all(status(asset) in _OFFLINE_STATES for asset in exact):
        ordered = sorted(
            exact,
            key=lambda asset: deb_asset_activity_at(asset)
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return selected(
            DebAvailabilityState.OFFLINE,
            ordered[0],
            "All exact DEB duplicate records currently report offline; the most "
            "recent record is selected as corroborating offline evidence.",
        )

    return DebAssetSelection(
        DebAvailabilityState.AMBIGUOUS,
        target,
        len(exact),
        None,
        None,
        None,
        None,
        "Multiple exact DEB assets contain current/conflicting availability "
        "evidence; Jason will not guess which asset is authoritative.",
    )
