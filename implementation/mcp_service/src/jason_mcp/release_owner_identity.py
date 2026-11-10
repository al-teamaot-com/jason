"""Exact, release-only Owner OAuth identity binding; no global admin alias.

The licensed AOT Owner user already has an active Microsoft Entra -> Jason
binding with existing execute/administer grants. Rebinding that identity to
person-al would move/bypass established grants. Instead, authorize that exact
authenticated subject for release approval *only*, never for other Owner-only
tools or authority grant administration.
"""
from __future__ import annotations

from collections.abc import Mapping

OWNER_TENANT_ID = "f7054323-d52b-4863-8c2f-1898f0b6077c"
LICENSED_OWNER_OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
LICENSED_OWNER_PRINCIPAL = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"


def authorized_release_owner(
    *,
    principal: str,
    organization_id: str,
    assurance: str,
    verified_token_claims: Mapping[str, object] | None,
    existing_owner_identities: frozenset[str],
) -> bool:
    """Return true only for an independently authenticated exact Owner subject.

    The upstream MCP middleware validates Entra signature, audience/issuer,
    token expiry, tenant, and active Jason identity/binding. This function
    enforces the exact release-only policy scope and rejects any caller-supplied
    email, alias, admin account or generic group membership as proof.
    """
    if (organization_id != "aot"
            or assurance != "entra-oauth-bearer"
            or not isinstance(verified_token_claims, Mapping)
            or verified_token_claims.get("tid") != OWNER_TENANT_ID
            or not isinstance(verified_token_claims.get("oid"), str)):
        return False
    oid = verified_token_claims["oid"]
    # Existing verified owner identities preserve their legacy semantics
    # only when the principal's bound token identity is internally consistent.
    if principal in existing_owner_identities:
        return principal == "person-al" or principal == (
            "person-entra-" + oid.replace("-", "").lower()
        )
    return (
        oid == LICENSED_OWNER_OID
        and principal == LICENSED_OWNER_PRINCIPAL
    )
