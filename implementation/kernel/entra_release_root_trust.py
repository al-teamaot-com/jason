"""Read-only host trust boundary for V5 admin-browser release signatures.

This extends existing Jason release authority; does NOT create approvals,
change root policy, deploy, or accept a decision in ApprovalRequestService.
"""
from __future__ import annotations

from base64 import b64decode
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_KEY_ID = re.compile(r"^[a-z][a-z0-9_.:-]{3,80}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UUID = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$")


class BrowserReleaseRootTrustDenied(PermissionError):
    pass


@dataclass(frozen=True)
class BrowserReleaseRootTrust:
    tenant_id: str
    admin_approver_oid: str
    organization_id: str
    reviewed_policy_sha256: str
    approved_key_ids: tuple[str, ...]
    keys: Mapping[str, Ed25519PublicKey]


def read_root_browser_release_trust(
    path: Path, *, expected_tenant_id: str,
    expected_admin_oid: str, expected_organization: str,
    expected_policy_sha256: str,
) -> BrowserReleaseRootTrust:
    """Load a distinct, already-reviewed root authorization for this key.

    The trust file must be separately approved through the existing Jason
    authority controls; this library never writes one or invents a default.
    """
    p = Path(path)
    try:
        meta = p.lstat()
    except OSError as exc:
        raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_ABSENT") from exc
    if (not stat.S_ISREG(meta.st_mode)
            or stat.S_IMODE(meta.st_mode) != 0o600
            or meta.st_uid not in (0, os.geteuid())
            or meta.st_size > 16384):
        raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_FILE_UNSAFE")
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_UNREADABLE") from exc
    expected = {
        "schema_version", "channel", "tenant_id", "admin_approver_oid",
        "organization_id", "reviewed_policy_sha256", "keys",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_SCHEMA_INVALID")
    if (value["schema_version"] != "1.0"
            or value["channel"] != "entra_browser_admin"
            or not isinstance(value["tenant_id"], str)
            or not _UUID.fullmatch(value["tenant_id"])
            or not isinstance(value["admin_approver_oid"], str)
            or not _UUID.fullmatch(value["admin_approver_oid"])
            or not isinstance(value["reviewed_policy_sha256"], str)
            or not _SHA.fullmatch(value["reviewed_policy_sha256"])
            or value["tenant_id"] != expected_tenant_id
            or value["admin_approver_oid"] != expected_admin_oid
            or value["organization_id"] != expected_organization
            or value["reviewed_policy_sha256"] != expected_policy_sha256):
        raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_REVIEWED_IDENTITY_MISMATCH")
    records = value["keys"]
    if not isinstance(records, list) or not 1 <= len(records) <= 3:
        raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_KEYS_INVALID")
    trusted = {}
    for item in records:
        if (not isinstance(item, dict)
                or set(item) != {"key_id", "public_key_b64", "state"}
                or not isinstance(item["key_id"], str)
                or not _KEY_ID.fullmatch(item["key_id"])
                or item["state"] != "active"
                or item["key_id"] in trusted):
            raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_KEY_NOT_APPROVED")
        raw = item["public_key_b64"]
        if not isinstance(raw, str) or len(raw) != 44:
            raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_KEY_FORMAT_INVALID")
        try:
            import base64
            public = base64.b64decode(raw, validate=True)
            if len(public) != 32:
                raise ValueError("public key size")
            trusted[item["key_id"]] = Ed25519PublicKey.from_public_bytes(public)
        except (ValueError, TypeError) as exc:
            raise BrowserReleaseRootTrustDenied("V5_ROOT_TRUST_KEY_FORMAT_INVALID") from exc
    return BrowserReleaseRootTrust(
        tenant_id=value["tenant_id"], admin_approver_oid=value["admin_approver_oid"],
        organization_id=value["organization_id"],
        reviewed_policy_sha256=value["reviewed_policy_sha256"],
        approved_key_ids=tuple(sorted(trusted)),
        keys=trusted,
    )
