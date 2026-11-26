"""Fixed PMv4 Owner issuer Docker projection; no generic writable bind API.

Reuses the existing MCP Entra session and already provisioned signing key.
Only the separately root-owned shadow control root is projected read-only,
except for its dedicated group-owned signed-decision receipt directory.
This module never provisions host state or creates a container.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

SHADOW_ROOT = Path("/var/lib/jason/pmv4-shadow")
DECISIONS = SHADOW_ROOT / "control/signed-owner-decisions"
AUDIENCE = Path("/etc/jason/pmv4-shadow/entra-audience.json")

# (source, destination, writable)
EXACT_MOUNTS = (
    (str(SHADOW_ROOT), str(SHADOW_ROOT), False),
    (str(DECISIONS), str(DECISIONS), True),
    (str(AUDIENCE), str(AUDIENCE), False),
)


def _trusted(path: Path, *, kind: str, group: int,
             group_writable: bool = False) -> None:
    try:
        meta = path.lstat()
    except OSError as exc:
        raise ValueError("PMV4_OWNER_PROJECTION_NOT_PROVISIONED") from exc
    mode = stat.S_IMODE(meta.st_mode)
    if (path.is_symlink() or meta.st_uid != 0 or meta.st_gid != group
            or bool(meta.st_mode & 0o002)
            or (stat.S_ISDIR(meta.st_mode) if kind == "dir"
                else stat.S_ISREG(meta.st_mode)) is False):
        raise ValueError("PMV4_OWNER_PROJECTION_UNTRUSTED")
    if group_writable:
        if mode != 0o770:
            raise ValueError("PMV4_OWNER_DECISION_DIRECTORY_MODE_INVALID")
    elif mode & 0o020:
        raise ValueError("PMV4_OWNER_PROJECTION_MUTABLE")
    if kind == "dir" and not (mode & 0o050):
        raise ValueError("PMV4_OWNER_PROJECTION_NOT_TRAVERSABLE")
    if kind == "file" and not (mode & 0o040):
        raise ValueError("PMV4_OWNER_AUDIENCE_NOT_GROUP_READABLE")


def validate_source(*, expected_audience: str, group: int = 1000) -> None:
    if (not isinstance(expected_audience, str)
            or not expected_audience.strip()):
        raise ValueError("PMV4_OWNER_AUDIENCE_UNPINNED")
    _trusted(SHADOW_ROOT, kind="dir", group=group)
    _trusted(SHADOW_ROOT / "control", kind="dir", group=group)
    _trusted(SHADOW_ROOT / "releases", kind="dir", group=group)
    _trusted(SHADOW_ROOT / "receipts", kind="dir", group=group)
    _trusted(DECISIONS, kind="dir", group=group, group_writable=True)
    _trusted(AUDIENCE.parent, kind="dir", group=group)
    _trusted(AUDIENCE, kind="file", group=group)
    try:
        raw = AUDIENCE.read_bytes()
        if len(raw) > 4096:
            raise ValueError("oversized")
        doc = json.loads(raw)
    except (ValueError, OSError) as exc:
        raise ValueError("PMV4_OWNER_AUDIENCE_INVALID") from exc
    if (not isinstance(doc, dict)
            or set(doc) != {"schema_version", "service", "audience"}
            or doc["schema_version"] != "1.0"
            or doc["service"] != "jason-pmv4-shadow"
            or doc["audience"] != expected_audience):
        raise ValueError("PMV4_OWNER_AUDIENCE_MISMATCH")


def add_projection_mounts(args: list[str], existing: dict[str, tuple[str, bool]],
                          *, expected_audience: str) -> None:
    validate_source(expected_audience=expected_audience)
    for src, dst, writable in EXACT_MOUNTS:
        if dst in existing:
            if existing[dst] == (src, writable):
                continue
            raise ValueError("PMV4_OWNER_EXISTING_MOUNT_CONFLICT")
        args.extend(["--mount",
                     "type=bind,src=" + src + ",dst=" + dst +
                     ("" if writable else ",readonly")])


def should_omit_existing(source: str, destination: str, writable: bool) -> bool:
    matching = [row for row in EXACT_MOUNTS if row[1] == destination]
    if not matching:
        return False
    expected = matching[0]
    if source != expected[0] or writable != expected[2]:
        raise ValueError("PMV4_OWNER_ROLLBACK_MOUNT_UNTRUSTED")
    return True
