"""Bounded owner-governed admin for exact read authority grants.

This is an operational fallback for cases where a newly deployed MCP admin tool
has not refreshed into the current ChatGPT tool catalog. It can only create an
OBSERVE grant for an exact active capability whose registry metadata explicitly
marks it read-only. It performs no provider access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from kernel.identity_authority import AuthorityGrant, PermissionMode
from jason_runtime.datto_component_approval_registry import approval_owner_identities

from .server import _runtime


class ReadAuthorityAdminError(RuntimeError):
    pass


def _grant_id(*, subject: str, capability: str, organization: str) -> str:
    material = "|".join((subject, capability, organization, "", "observe", "no-approval"))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"grant_exact_{digest}"


def grant_exact_read_authority(
    *,
    subject_id: str,
    capability: str,
    approved_by: str,
) -> tuple[AuthorityGrant, bool]:
    actor = str(approved_by or "").strip()
    owners = approval_owner_identities()
    if not owners or actor not in owners:
        raise ReadAuthorityAdminError("AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED")

    app = _runtime()
    subject = str(subject_id or "").strip()
    identity = app.identity_authority.identities.get(subject)
    if identity is None or identity.status != "active":
        raise ReadAuthorityAdminError("AUTHORITY_GRANT_ACTIVE_SUBJECT_REQUIRED")

    exact = str(capability or "").strip()
    if not exact or any(token in exact for token in ("*", "?", "[", "]")):
        raise ReadAuthorityAdminError("AUTHORITY_GRANT_EXACT_CAPABILITY_REQUIRED")
    matches = [
        item
        for item in app.capabilities.list_all()
        if item.capability_name == exact
        and item.lifecycle_status.value == "active"
    ]
    if len(matches) != 1:
        raise ReadAuthorityAdminError("AUTHORITY_GRANT_ACTIVE_CAPABILITY_REQUIRED")
    definition = matches[0]
    if str((definition.metadata or {}).get("read_only", "")).casefold() != "true":
        raise ReadAuthorityAdminError("AUTHORITY_GRANT_READ_ONLY_REQUIRED")

    organization = identity.organization_id
    grant_id = _grant_id(
        subject=subject,
        capability=exact,
        organization=organization,
    )
    candidate = AuthorityGrant(
        grant_id=grant_id,
        subject_id=subject,
        capability=exact,
        organization_id=organization,
        client_id=None,
        permission=PermissionMode.OBSERVE,
        approval_required=False,
        status="active",
    )
    repo = app.identity_authority.grants
    existing = repo.get(grant_id)
    if existing is not None:
        if existing == candidate:
            return existing, False
        raise ReadAuthorityAdminError("AUTHORITY_GRANT_ID_CONFLICT")

    audit = app.identity_authority.audit
    if audit is None:
        raise ReadAuthorityAdminError("AUTHORITY_GRANT_AUDIT_UNAVAILABLE")
    audit.append_authority_audit(
        event_type="authority.grant.create.requested",
        correlation_id=f"authority-admin:{grant_id}",
        principal_id=actor,
        organization_id=organization,
        capability=exact,
        outcome="succeeded",
        reason_codes=("EXACT_READ_GRANT_ADMIN", f"GRANT_ID:{grant_id}"),
    )
    repo.put(candidate)
    audit.append_authority_audit(
        event_type="authority.grant.created",
        correlation_id=f"authority-admin:{grant_id}",
        principal_id=actor,
        organization_id=organization,
        capability=exact,
        outcome="succeeded",
        reason_codes=("EXACT_READ_GRANT_ADMIN", f"GRANT_ID:{grant_id}"),
    )
    return candidate, True


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capability")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--approved-by", required=True)
    args = parser.parse_args()
    grant, created = grant_exact_read_authority(
        subject_id=args.subject,
        capability=args.capability,
        approved_by=args.approved_by,
    )
    print(json.dumps({
        "status": "succeeded",
        "created": created,
        "grant_id": grant.grant_id,
        "subject_id": grant.subject_id,
        "capability": grant.capability,
        "organization_id": grant.organization_id,
        "permission": grant.permission.value,
        "approval_required": grant.approval_required,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
