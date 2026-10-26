"""Fail-closed, shared host/runtime safety hold for owner Teams release approvals.

This is a *revocation guard*, not a source of owner authority. It is deliberately
independent of the existing private 0600 owner approval policy and is read from
the release manager state mount by BOTH the runtime and host release consumer.

A reviewed, governed maintenance action may install or update this 0600 file.
A missing file preserves preexisting opt-in functionality for backward
compatibility; malformed/insecure files fail closed and cannot enable approval.
A durable "released" record carries the hold epoch, permanently invalidating
all previously issued approval requests. Never remove the record to release a
hold: update it only through separately authorized change control.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat


HOLD_FILENAME = "owner-release-approval-containment.json"
CAPABILITY = "release.production.approve"
HOLD_ID_PATTERN = re.compile(r"^P0-[0-9]{3,8}$")


@dataclass(frozen=True, slots=True)
class ReleaseApprovalContainment:
    state: str = "not_configured"
    hold_id: str | None = None
    hold_started_at: datetime | None = None
    released_at: datetime | None = None

    @property
    def active(self) -> bool:
        return self.state == "held"

    def require_can_issue(self) -> None:
        if self.active:
            raise PermissionError("owner_release_approval_hold_active:" + (self.hold_id or "unknown"))

    def is_request_eligible(self, requested_at: datetime) -> bool:
        if not isinstance(requested_at, datetime) or requested_at.tzinfo is None:
            return False
        if self.active:
            return False
        # A release of a hold is NOT a replay permit for a pre-hold approved
        # receipt, even if the Teams decision was valid and previously signed.
        if self.released_at is not None and requested_at <= self.released_at:
            return False
        return True

    def require_request_eligible(self, requested_at: datetime) -> None:
        self.require_can_issue()
        if not self.is_request_eligible(requested_at):
            raise PermissionError("owner_release_approval_pre_hold_request_revoked")


def _strict_instant(value: object) -> datetime:
    if not isinstance(value, str) or not 20 <= len(value) <= 40:
        raise PermissionError("approval containment time must be UTC ISO 8601")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PermissionError("approval containment time invalid") from exc
    if instant.tzinfo is None or instant.utcoffset() != timezone.utc.utcoffset(instant):
        raise PermissionError("approval containment timestamp must be UTC")
    if not 2026 <= instant.year <= 2100:
        raise PermissionError("approval containment timestamp outside bound")
    return instant


def read_release_approval_containment(state_root: Path) -> ReleaseApprovalContainment:
    path = Path(state_root) / HOLD_FILENAME
    try:
        info = path.lstat()
    except FileNotFoundError:
        # No emergency hold has ever been activated in this environment.
        return ReleaseApprovalContainment()

    if (not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid not in (0, os.geteuid())
            or info.st_size > 4096):
        raise PermissionError("owner_release_approval_containment_policy_invalid")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError, OSError) as exc:
        raise PermissionError("owner_release_approval_containment_policy_invalid") from exc
    keys = {"schema_version", "capability", "state", "hold_id", "hold_started_at"}
    if not isinstance(raw, dict) or (
        set(raw) not in (keys, keys | {"released_at"})
    ):
        raise PermissionError("owner_release_approval_containment_policy_invalid")
    if (raw["schema_version"] != "1.0" or raw["capability"] != CAPABILITY
            or raw["state"] not in ("held", "released")
            or not isinstance(raw["hold_id"], str)
            or HOLD_ID_PATTERN.fullmatch(raw["hold_id"]) is None):
        raise PermissionError("owner_release_approval_containment_policy_invalid")
    start = _strict_instant(raw["hold_started_at"])
    if raw["state"] == "held":
        if "released_at" in raw:
            raise PermissionError("held containment cannot carry release timestamp")
        return ReleaseApprovalContainment(state="held", hold_id=raw["hold_id"],
                                          hold_started_at=start)
    if "released_at" not in raw:
        raise PermissionError("released containment missing durable revocation watermark")
    released = _strict_instant(raw["released_at"])
    if released <= start:
        raise PermissionError("containment release must be after hold")
    return ReleaseApprovalContainment(
        state="released", hold_id=raw["hold_id"],
        hold_started_at=start, released_at=released,
    )
