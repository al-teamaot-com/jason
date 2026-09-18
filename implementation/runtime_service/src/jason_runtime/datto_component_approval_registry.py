from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


DATTO_COMPONENT_APPROVAL_REGISTRY_PATH_ENV = (
    "JASON_DATTO_COMPONENT_APPROVAL_REGISTRY_PATH"
)
DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES_ENV = (
    "JASON_DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES"
)
DEFAULT_DATTO_COMPONENT_APPROVAL_REGISTRY_PATH = (
    "/var/lib/jason/authority/datto-component-approvals.json"
)
REGISTRY_VERSION = 1


class DattoComponentApprovalRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DattoComponentApprovalRecord:
    uid: str
    name: str
    status: str
    approved_by: str
    approved_at: str
    metadata_fingerprint: str
    reason: str = ""
    revoked_by: str | None = None
    revoked_at: str | None = None
    revoke_reason: str | None = None


def registry_path() -> Path:
    configured = os.getenv(
        DATTO_COMPONENT_APPROVAL_REGISTRY_PATH_ENV,
        "",
    ).strip()
    return Path(
        configured
        or DEFAULT_DATTO_COMPONENT_APPROVAL_REGISTRY_PATH
    )


def approval_owner_identities() -> frozenset[str]:
    raw = os.getenv(
        DATTO_COMPONENT_APPROVAL_OWNER_IDENTITIES_ENV,
        "",
    )
    return frozenset(
        item.strip()
        for item in raw.split(",")
        if item.strip()
    )


def component_metadata_fingerprint(
    record: Mapping[str, Any],
) -> str:
    """Hash only reviewable, non-secret component metadata.

    Datto's governed component catalog does not expose an immutable script
    revision today. This fingerprint therefore binds standing approval to the
    metadata Jason can safely review: durable UID/name, description, category,
    credential requirement, and the input-variable contract. Any change to
    those fields invalidates the old unsupervised approval and falls back to
    per-run approval.
    """

    normalized = {
        "resource_id": str(
            record.get("resource_id") or ""
        ).strip(),
        "name": str(record.get("name") or "").strip(),
        "description": str(
            record.get("description") or ""
        ).strip(),
        "category": str(record.get("category") or "").strip(),
        "credentials_required": (
            record.get("credentials_required")
            if isinstance(
                record.get("credentials_required"),
                bool,
            )
            else None
        ),
        "variables": record.get("variables")
        if isinstance(record.get("variables"), list)
        else [],
    }
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _record_from_mapping(
    raw: Mapping[str, Any],
) -> DattoComponentApprovalRecord:
    allowed = {
        "uid",
        "name",
        "status",
        "approved_by",
        "approved_at",
        "metadata_fingerprint",
        "reason",
        "revoked_by",
        "revoked_at",
        "revoke_reason",
    }
    if set(raw) - allowed:
        raise DattoComponentApprovalRegistryError(
            "DATTO_COMPONENT_APPROVAL_REGISTRY_INVALID"
        )

    uid = str(raw.get("uid") or "").strip()
    name = str(raw.get("name") or "").strip()
    status = str(raw.get("status") or "").strip().casefold()
    approved_by = str(raw.get("approved_by") or "").strip()
    approved_at = str(raw.get("approved_at") or "").strip()
    fingerprint = str(
        raw.get("metadata_fingerprint") or ""
    ).strip().casefold()

    if (
        not uid
        or not name
        or status not in {"approved", "revoked"}
        or not approved_by
        or not approved_at
        or len(fingerprint) != 64
        or any(ch not in "0123456789abcdef" for ch in fingerprint)
    ):
        raise DattoComponentApprovalRegistryError(
            "DATTO_COMPONENT_APPROVAL_REGISTRY_INVALID"
        )

    return DattoComponentApprovalRecord(
        uid=uid,
        name=name,
        status=status,
        approved_by=approved_by,
        approved_at=approved_at,
        metadata_fingerprint=fingerprint,
        reason=str(raw.get("reason") or "").strip(),
        revoked_by=(
            str(raw.get("revoked_by") or "").strip()
            or None
        ),
        revoked_at=(
            str(raw.get("revoked_at") or "").strip()
            or None
        ),
        revoke_reason=(
            str(raw.get("revoke_reason") or "").strip()
            or None
        ),
    )


def _load_payload(path: Path | None = None) -> dict[str, Any]:
    selected = path or registry_path()
    if not selected.exists():
        return {"version": REGISTRY_VERSION, "records": []}
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise DattoComponentApprovalRegistryError(
            "DATTO_COMPONENT_APPROVAL_REGISTRY_INVALID"
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("version") != REGISTRY_VERSION
        or not isinstance(payload.get("records"), list)
    ):
        raise DattoComponentApprovalRegistryError(
            "DATTO_COMPONENT_APPROVAL_REGISTRY_INVALID"
        )
    # Validate every persisted record before any policy decision uses it.
    for item in payload["records"]:
        if not isinstance(item, Mapping):
            raise DattoComponentApprovalRegistryError(
                "DATTO_COMPONENT_APPROVAL_REGISTRY_INVALID"
            )
        _record_from_mapping(item)
    return payload


def list_records(
    path: Path | None = None,
) -> tuple[DattoComponentApprovalRecord, ...]:
    payload = _load_payload(path)
    return tuple(
        _record_from_mapping(item)
        for item in payload["records"]
    )


def latest_records_by_identity(
    path: Path | None = None,
) -> dict[tuple[str, str], DattoComponentApprovalRecord]:
    latest: dict[tuple[str, str], DattoComponentApprovalRecord] = {}
    for item in list_records(path):
        latest[(item.uid, item.name.casefold())] = item
    return latest


def _write_payload(
    payload: Mapping[str, Any],
    path: Path | None = None,
) -> None:
    selected = path or registry_path()
    selected.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(selected.parent),
        prefix=selected.name + ".",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temp = Path(handle.name)
    os.chmod(temp, 0o600)
    os.replace(temp, selected)


def approve_component(
    *,
    uid: str,
    name: str,
    approved_by: str,
    metadata_fingerprint: str,
    reason: str = "",
    path: Path | None = None,
) -> DattoComponentApprovalRecord:
    payload = _load_payload(path)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {
        "uid": str(uid).strip(),
        "name": str(name).strip(),
        "status": "approved",
        "approved_by": str(approved_by).strip(),
        "approved_at": now,
        "metadata_fingerprint": str(metadata_fingerprint).strip().casefold(),
        "reason": str(reason or "").strip(),
        "revoked_by": None,
        "revoked_at": None,
        "revoke_reason": None,
    }
    parsed = _record_from_mapping(record)
    payload["records"].append(record)
    _write_payload(payload, path)
    return parsed


def revoke_component(
    *,
    uid: str,
    name: str,
    revoked_by: str,
    reason: str = "",
    path: Path | None = None,
) -> DattoComponentApprovalRecord:
    payload = _load_payload(path)
    records = list_records(path)
    matches = [
        item
        for item in records
        if item.uid == str(uid).strip()
        and item.name.casefold() == str(name).strip().casefold()
        and item.status == "approved"
    ]
    if not matches:
        # A revocation may also intentionally downgrade a source-configured
        # standing-safe component. Use a zero fingerprint only when the caller
        # supplies the current reviewed fingerprint separately through approval;
        # therefore source-only revocation is represented with a deterministic
        # sentinel fingerprint.
        fingerprint = "0" * 64
        approved_by = "source-config"
        approved_at = "1970-01-01T00:00:00Z"
    else:
        latest = matches[-1]
        fingerprint = latest.metadata_fingerprint
        approved_by = latest.approved_by
        approved_at = latest.approved_at

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    record = {
        "uid": str(uid).strip(),
        "name": str(name).strip(),
        "status": "revoked",
        "approved_by": approved_by,
        "approved_at": approved_at,
        "metadata_fingerprint": fingerprint,
        "reason": "",
        "revoked_by": str(revoked_by).strip(),
        "revoked_at": now,
        "revoke_reason": str(reason or "").strip(),
    }
    parsed = _record_from_mapping(record)
    payload["records"].append(record)
    _write_payload(payload, path)
    return parsed
