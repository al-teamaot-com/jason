"""AOT technician attestation for an exact client-requested standard user.

This is a control-plane record in the existing JKD-001 ApprovalRepository.
It never creates a provider identity and never bypasses execution approval.
A technician must have a pre-existing exact client-scoped execute grant and
affirm the customer authorization checked in the referenced service ticket.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from kernel.identity_authority import ApprovalRecord, PermissionMode


_TICKET = re.compile(r"T[0-9]{8}\.[0-9]{4}\Z")
_UPN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}@[A-Za-z0-9.-]{3,253}\Z")
_CLIENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def attest_approved_standard_user_request(
    *, authority, principal_id: str, organization_id: str,
    authenticated_client_id: str | None, client_id: str,
    ticket_number: str, user_principal_name: str,
    customer_contact_id: int, contact_verified: bool,
    clock=lambda: datetime.now(timezone.utc),
) -> dict[str, str]:
    if organization_id != "aot" or not principal_id.strip():
        raise PermissionError("ONBOARDING_AOT_TECHNICIAN_REQUIRED")
    identity = authority.identities.get(principal_id)
    if (identity is None or identity.status != "active"
            or identity.organization_id != "aot"
            or identity.identity_type not in ("person", "human")):
        raise PermissionError("ONBOARDING_ACTIVE_AOT_TECHNICIAN_REQUIRED")
    if (not isinstance(client_id, str) or not _CLIENT.fullmatch(client_id)
            or authenticated_client_id not in (None, client_id)):
        raise PermissionError("ONBOARDING_CLIENT_BOUNDARY_INVALID")
    if (not isinstance(ticket_number, str)
            or not _TICKET.fullmatch(ticket_number)):
        raise ValueError("ONBOARDING_AUTOTASK_TICKET_NUMBER_INVALID")
    if (not isinstance(user_principal_name, str)
            or not _UPN.fullmatch(user_principal_name.strip())):
        raise ValueError("ONBOARDING_UPN_INVALID")
    if (isinstance(customer_contact_id, bool)
            or not isinstance(customer_contact_id, int)
            or customer_contact_id <= 0):
        raise ValueError("ONBOARDING_CLIENT_CONTACT_ID_INVALID")
    if contact_verified is not True:
        raise PermissionError("ONBOARDING_CLIENT_AUTHORIZATION_NOT_ATTESTED")

    now = clock()
    if now.tzinfo is None:
        raise ValueError("ONBOARDING_TIMEZONE_REQUIRED")
    client_grants = [
        grant
        for subject in (principal_id, "organization:aot")
        for grant in authority.grants.list_for_subject(subject)
        if (grant.capability == "identity.user.create"
            and grant.organization_id == organization_id
            and grant.client_id == client_id
            and grant.permission is PermissionMode.EXECUTE
            and grant.approval_required is True
            and grant.status == "active"
            and (grant.effective_from is None or grant.effective_from <= now)
            and (grant.effective_until is None or grant.effective_until > now))
    ]
    if not client_grants:
        raise PermissionError("ONBOARDING_EXACT_CLIENT_GRANT_REQUIRED")

    approvals = authority.approvals
    if not callable(getattr(approvals, "put", None)):
        raise RuntimeError("ONBOARDING_APPROVAL_STORE_NOT_WRITABLE")
    audit = authority.audit
    if not callable(getattr(audit, "append_authority_audit", None)):
        raise RuntimeError("ONBOARDING_AUDIT_REQUIRED")
    upn = user_principal_name.strip().casefold()
    approval_id = "REQ-" + uuid4().hex
    record = ApprovalRecord(
        approval_id=approval_id,
        request_id="upn:" + upn,
        capability="identity.user.create",
        organization_id="aot",
        client_id=client_id,
        requested_by=principal_id,
        status="approved",
        decided_by=principal_id,
        decided_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    # Audit provenance without leaking a password or other secret.
    audit.append_authority_audit(
        event_type="onboarding.client_request.attested",
        correlation_id=f"onboarding:{approval_id}",
        principal_id=principal_id,
        organization_id=organization_id,
        capability="identity.user.create",
        outcome="approved_attestation",
        reason_codes=(
            f"TICKET:{ticket_number}",
            f"CONTACT_ID:{customer_contact_id}",
            f"CLIENT_ID:{client_id}",
        ),
    )
    approvals.put(record)
    return {
        "onboarding_request_id": approval_id,
        "client_id": client_id,
        "source_ticket": ticket_number,
        "user_principal_name": upn,
        "authorization": "technician_attestation_recorded",
        "expires_at": record.expires_at.isoformat(),
    }
