from datetime import datetime, timedelta, timezone

import pytest

from kernel.identity_authority import (
    AuthorityGrant, IdentityAuthorityService, IdentityRecord,
    InMemoryIdentityRepository, InMemoryApprovalRepository,
    InMemoryAuthorityGrantRepository, PermissionMode,
)
from orchestrator.onboarding_request_attestation import (
    attest_approved_standard_user_request,
)


class Audit:
    def __init__(self): self.events=[]
    def append_authority_audit(self, **kwargs): self.events.append(kwargs)


def context():
    ids=InMemoryIdentityRepository()
    ids.put(IdentityRecord("tech-1", "human", "aot"))
    ids.put(IdentityRecord("autonomy", "service", "aot"))
    grants=InMemoryAuthorityGrantRepository()
    grants.put(AuthorityGrant(
        "exact-client-create", "tech-1", "identity.user.create",
        "aot", "client-1", PermissionMode.EXECUTE, approval_required=True,
    ))
    approvals=InMemoryApprovalRepository()
    audit=Audit()
    authority=IdentityAuthorityService(
        identities=ids, grants=grants, approvals=approvals, audit=audit,
    )
    return authority, approvals, audit


def submit(authority, **kwargs):
    args={
        "authority":authority,
        "principal_id":"tech-1",
        "organization_id":"aot",
        "authenticated_client_id":None,
        "client_id":"client-1",
        "ticket_number":"T20261028.0048",
        "user_principal_name":"jane.smith@client.test",
        "customer_contact_id":25,
        "contact_verified":True,
    }
    args.update(kwargs)
    return attest_approved_standard_user_request(**args)


def test_attested_exact_user_client_is_durable_short_lived_and_audited():
    authority, approvals, audit = context()
    receipt=submit(authority)
    record=approvals.get(receipt["onboarding_request_id"])
    assert record.status=="approved"
    assert record.capability=="identity.user.create"
    assert record.client_id=="client-1"
    assert record.requested_by=="tech-1"
    assert record.request_id=="upn:jane.smith@client.test"
    assert (record.expires_at-record.decided_at)==timedelta(minutes=30)
    assert receipt["authorization"]=="technician_attestation_recorded"
    assert audit.events[0]["event_type"]=="onboarding.client_request.attested"
    assert "password" not in str(audit.events)
    assert "jane.smith" not in str(audit.events)


@pytest.mark.parametrize("override", [
    {"principal_id":"autonomy"},
    {"principal_id":"missing"},
    {"organization_id":"other"},
    {"client_id":"different-client"},
    {"client_id":"*"},
    {"authenticated_client_id":"another"},
    {"ticket_number":"wrong"},
    {"user_principal_name":"bad"},
    {"contact_verified":False},
    {"contact_verified":"true"},
    {"customer_contact_id":0},
    {"customer_contact_id":True},
])
def test_invalid_identity_request_and_attestation_fail_without_record(override):
    authority, approvals, audit = context()
    with pytest.raises((PermissionError, ValueError)):
        submit(authority, **override)
    assert not audit.events


def test_without_preexisting_exact_grant_no_approval_can_be_created():
    authority, approvals, audit = context()
    authority.grants.revoke("exact-client-create")
    with pytest.raises(PermissionError, match="EXACT_CLIENT_GRANT_REQUIRED"):
        submit(authority)
    assert not audit.events


def test_grant_for_another_client_is_not_inherited():
    authority, approvals, audit = context()
    with pytest.raises(PermissionError):
        submit(authority, client_id="client-2")


def test_expired_grant_not_accepted():
    authority, approvals, audit = context()
    authority.grants.revoke("exact-client-create")
    authority.grants.put(AuthorityGrant(
        "expired-client-create", "tech-1", "identity.user.create",
        "aot", "client-1", PermissionMode.EXECUTE, approval_required=True,
        effective_until=datetime.now(timezone.utc)-timedelta(minutes=1),
    ))
    with pytest.raises(PermissionError):
        submit(authority)
