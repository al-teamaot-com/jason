"""Opt-in, self-only Autotask catalog grant administration for one verified Owner.

This does not create a new Owner role or grant provider execution permission.
The ordinary authenticated requester is permitted to administer at most four
exact catalog execute grants for their own active AOT identity. The existing
per-execution approval and provider controls remain separate and mandatory.
"""
from __future__ import annotations

import os
from typing import Mapping
from uuid import UUID

PROFILE_ENV = "JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE"
PROFILE = "aot-catalog-self-owner-v1"
EXPECTED_TENANT_ID = "f7054323-d52b-4863-8c2f-1898f0b6077c"
EXPECTED_OBJECT_ID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
EXPECTED_PRINCIPAL = "person-entra-" + UUID(EXPECTED_OBJECT_ID).hex
CATALOG_CAPABILITIES = frozenset({
    "service.service.create",
    "service.service.update",
    "service.service.bundle.create",
    "service.service.bundle.update",
})


class CatalogGrantAdminDenied(PermissionError):
    """Authorization denied before grant repository write or provider contact."""


def _canonical_uuid(value: object) -> str:
    if not isinstance(value, str):
        return ""
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        return ""


def verify_catalog_grant_admin_actor(
    *, principal: str, organization: str, assurance: str, client_id: str | None,
    claims: Mapping[str, object], admin_profile: str,
) -> tuple[str, str]:
    """Verify the exact existing Entra Owner in an already authenticated MCP call.

    Caller obtains principal through the original Entra binding, not from an
    argument, forwarded email, ChatGPT text, or requester supplied claim.
    The default is disabled; unknown modes and V4 admin-mode collisions deny.
    """
    setting = os.getenv(PROFILE_ENV, "").strip()
    if not setting:
        raise CatalogGrantAdminDenied("AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED")
    if setting != PROFILE:
        raise CatalogGrantAdminDenied("CATALOG_GRANT_ADMIN_PROFILE_INVALID")
    if admin_profile != "":
        raise CatalogGrantAdminDenied("CATALOG_GRANT_ADMIN_POLICY_CONFLICT")
    if (
        principal != EXPECTED_PRINCIPAL or organization != "aot"
        or assurance != "entra-oauth-bearer" or client_id is not None
        or not isinstance(claims, Mapping)
        or _canonical_uuid(claims.get("tid")) != EXPECTED_TENANT_ID
        or _canonical_uuid(claims.get("oid")) != EXPECTED_OBJECT_ID
    ):
        raise CatalogGrantAdminDenied("CATALOG_GRANT_ADMIN_IDENTITY_DENIED")
    return principal, organization


def require_catalog_grant_scope(
    *, actor: str, subject: str, capability: str, permission: str,
    approval_required: bool, client_id: str | None,
) -> None:
    """Never grant another identity, category, client, or implicit approval."""
    if (
        actor != EXPECTED_PRINCIPAL or subject != actor
        or capability not in CATALOG_CAPABILITIES
        or permission != "execute" or approval_required is not True
        or client_id is not None
    ):
        raise CatalogGrantAdminDenied("CATALOG_GRANT_ADMIN_SCOPE_DENIED")


def catalog_visible_grant(*, actor: str, grant: object) -> bool:
    return bool(
        getattr(grant, "subject_id", None) == actor
        and getattr(grant, "organization_id", None) == "aot"
        and getattr(grant, "capability", None) in CATALOG_CAPABILITIES
        and getattr(getattr(grant, "permission", None), "value", None) == "execute"
        and getattr(grant, "approval_required", None) is True
        and getattr(grant, "client_id", "invalid") is None
    )
