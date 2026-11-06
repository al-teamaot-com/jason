"""Tenant-scoped approval routing policy; never an identity authority source.

Returns candidate identity IDs only. Each candidate MUST still be verified via
Microsoft Entra and JKD-001 before approving anything.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantApprovalPolicy:
    organization_id: str
    role_members: dict[str, frozenset[str]]
    capability_roles: dict[str, frozenset[str]]
    disabled_principals: frozenset[str] = frozenset()

    def __post_init__(self):
        if not self.organization_id or not self.capability_roles:
            raise ValueError('explicit tenant and approval policy required')


def route_approval_candidates(*, policy: TenantApprovalPolicy, organization_id: str,
        capability: str, requester_identity_id: str) -> tuple[str, ...]:
    """Select tenant-configured candidates, excluding requester and disabled users.

    Does not verify whether a user is logged in, possesses Teams, or may approve.
    """
    if organization_id != policy.organization_id:
        raise PermissionError('approval routing tenant mismatch')
    roles = policy.capability_roles.get(capability)
    if not roles:
        raise PermissionError('no configured approval role for capability')
    if not requester_identity_id:
        raise PermissionError('authenticated requester required')
    candidates = set()
    for role in roles:
        candidates.update(policy.role_members.get(role, frozenset()))
    candidates.difference_update(policy.disabled_principals)
    candidates.discard(requester_identity_id)
    if not candidates:
        raise PermissionError('no available approval candidates')
    return tuple(sorted(candidates))
