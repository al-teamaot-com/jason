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
import subprocess

OFF = "off|false|none"
SESSION = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{4,88}$")
IMMUTABLE_RELEASES_ROOT = Path("/opt/jason/releases")
MANAGED_SOURCE_GIT = Path("/home/al/.local/lib/jason/engineering-worker-source")

EXPECTED_KEYS = frozenset({
    "schema_version", "enabled", "purpose", "organization_id",
    "owner_identity_id", "requester_identity_id", "capability",
    "execution_permitted", "session_id", "expires_at",
})


def verify_source_pinned_manifest(path: Path, source_revision: str) -> None:
    """Reject a runtime-edited manifest; trust only the reviewed Git blob."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_revision):
        raise ValueError("an exact immutable release revision is required")
    root = Path(__file__).resolve().parents[1]
    canonical = root / "config" / "owner-uat-campaign.json"
    if path.is_symlink() or path.absolute() != canonical:
        raise PermissionError("UAT manifest must come from the exact release tree")
    # Production packages are immutable /opt/jason/releases/<exact_sha> trees,
    # NOT Git worktrees: they intentionally contain no .git directory.
    # Read only the immutable SHA blob from the managed source repository.
    # Local/test worktrees still pin against their own Git objects.
    if root.parent == IMMUTABLE_RELEASES_ROOT:
        if root.name != source_revision or root.is_symlink():
            raise PermissionError("UAT campaign does not belong to the approved immutable release")
        source_git = MANAGED_SOURCE_GIT
    elif (root / ".git").exists():
        source_git = root
    else:
        raise PermissionError("UAT campaign not in a trusted Git or immutable release tree")
    try:
        expected = subprocess.check_output([
            "/usr/bin/git", "-C", str(source_git), "show",
            source_revision + ":config/owner-uat-campaign.json",
        ], timeout=15, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise PermissionError("reviewed UAT Git object unavailable") from exc
    if len(expected) > 4096 or path.read_bytes() != expected:
        raise PermissionError("UAT manifest differs from approved source revision")


def activate_from_manifest(
    path: Path, *, now: datetime | None = None, preflight: bool = False
) -> str:
    """Return a shell-parseable bounded tuple; never accept arbitrary env."""
    if preflight or not path.exists():
        return OFF
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("UAT manifest must be a small regular tracked source file")
    if path.stat().st_mode & stat.S_IWOTH:
        raise PermissionError("UAT activation source is world writable")
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
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if not args.preflight and args.manifest.exists():
        verify_source_pinned_manifest(args.manifest, args.source_revision)
    print(activate_from_manifest(args.manifest, preflight=args.preflight))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
