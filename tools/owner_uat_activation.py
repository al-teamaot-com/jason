#!/usr/bin/env python3
"""Immutable release-source activation for one nonexecuting Owner Teams UAT.

Only the canonical production deploy script reads this source-committed
manifest. It emits three strictly bounded runtime environment values.
This is not an API, a Teams approval decision, or execution authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import stat

OFF = "off|false|none"
SESSION = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{4,88}$")
EXPECTED_KEYS = frozenset({
    "schema_version", "enabled", "purpose", "organization_id",
    "owner_identity_id", "requester_identity_id", "capability",
    "execution_permitted", "session_id", "expires_at",
})


def activate_from_manifest(
    path: Path, *, now: datetime | None = None, preflight: bool = False
) -> str:
    """Return a shell-parseable bounded tuple; never accept arbitrary env."""
    if preflight or not path.exists():
        return OFF
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("UAT manifest must be a small regular tracked source file")
    if path.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise PermissionError("UAT activation source is group/world writable")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != EXPECTED_KEYS:
        raise ValueError("UAT manifest has unknown or missing fields")
    if data.get("schema_version") != "1.0" or type(data.get("enabled")) is not bool:
        raise ValueError("UAT activation schema/enable flag invalid")
    if not data["enabled"]:
        return OFF
    expected = {
        "purpose": "owner_teams_nonexecuting_uat",
        "organization_id": "aot",
        "owner_identity_id": "person-al",
        "requester_identity_id": "svc-jason-acceptance-test",
        "capability": "interaction.owner.acceptance.record",
        "execution_permitted": False,
    }
    if any(data.get(key) != value for key, value in expected.items()):
        raise PermissionError("UAT manifest attempted to broaden test-only authority")
    sid = data.get("session_id")
    if not isinstance(sid, str) or SESSION.fullmatch(sid) is None:
        raise ValueError("UAT session ID is missing or unsafe")
    try:
        expiration = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("UAT expiration invalid") from exc
    if expiration.tzinfo is None or expiration.utcoffset() != timedelta(0):
        raise ValueError("UAT must expire at a UTC instant")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("UTC clock required")
    if current >= expiration:
        return OFF
    if expiration - current > timedelta(hours=48):
        raise ValueError("UAT activation campaign exceeds 48 hours")
    return "nonexecuting_test_only|true|" + sid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    print(activate_from_manifest(args.manifest, preflight=args.preflight))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
