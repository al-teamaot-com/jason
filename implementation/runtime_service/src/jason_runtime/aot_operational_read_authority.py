"""Standing observe-only provider reads for authenticated AOT human staff.

Owner policy (2026-10-28): operational information/status from Datto RMM,
Datto EDR/AV, BackupIQ, Autotask, IT Glue, Microsoft 365 and other approved
read-only external providers must be available without individual read grants.
This policy never grants mutation, remote script execution, credentials, or
access beyond source-side data authorization and logged-in organization scope.
"""

from kernel.identity_authority import AuthorityGrant, PermissionMode
from orchestrator.provider_read_authority import AOT_TECHNICIAN_OPERATIONAL_READ_POLICY


AOT_TECHNICIAN_READ_GRANT_ID = "grant-aot-human-operational-provider-observe-v1"


def ensure_aot_technician_read_authority(identity_authority) -> bool:
    """Create the single standing AOT policy idempotently; conflicts fail closed."""
    grant = AuthorityGrant(
        grant_id=AOT_TECHNICIAN_READ_GRANT_ID,
        subject_id="organization:aot",
        capability=AOT_TECHNICIAN_OPERATIONAL_READ_POLICY,
        organization_id="aot",
        client_id=None,
        permission=PermissionMode.OBSERVE,
        approval_required=False,
        status="active",
    )
    existing = identity_authority.grants.get(grant.grant_id)
    if existing is None:
        identity_authority.grants.put(grant)
        return True
    if existing != grant:
        raise RuntimeError("AOT technician read-only grant conflicts with immutable policy")
    return False
