"""Jason Owner sign-in is independent of Entra/M365 administrative identity.

Source-level tests only; never write to production or modify Microsoft identity.
"""
from types import SimpleNamespace

import pytest
from jason_mcp import server

TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
LICENSED_OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
LICENSED_PRINCIPAL = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"
M365_ADMIN_OID = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
M365_ADMIN_PRINCIPAL = "person-al"  # Live legacy binding; NOT a Jason Owner grant


def authenticated(monkeypatch, *, principal=LICENSED_PRINCIPAL,
                  oid=LICENSED_OID, tenant=TENANT, organization="aot",
                  assurance="entra-oauth-bearer", client_id=None,
                  profile="jason-owner-v1", token_present=True):
    monkeypatch.setenv("JASON_AOT_ADMIN_APPROVER_PROFILE", profile)
    monkeypatch.setattr(server, "_authenticated_write_identity",
                        lambda: (principal, organization, assurance, client_id))
    monkeypatch.setattr(server, "get_access_token",
                        lambda: (SimpleNamespace(claims={"tid": tenant, "oid": oid})
                                 if token_present else None))
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-al"}))


def test_exact_licensed_owner_can_administer_jason_through_new_profile(monkeypatch):
    authenticated(monkeypatch)
    assert server._authority_admin_owner() == (LICENSED_PRINCIPAL, "aot")
    assert server._component_approval_owner() == (LICENSED_PRINCIPAL, "aot")
    assert server._release_approval_owner() == (LICENSED_PRINCIPAL, "aot")


@pytest.mark.parametrize("changes", [
    {"principal": M365_ADMIN_PRINCIPAL, "oid": M365_ADMIN_OID},
    {"principal": "person-entra-c848022de13b445784b0e2f5c00dcaf6", "oid": M365_ADMIN_OID},
    {"principal": "person-al", "oid": LICENSED_OID},
    {"principal": "person-other"},
    {"oid": M365_ADMIN_OID},
    {"tenant": "00000000-0000-4000-8000-000000000000"},
    {"organization": "not-aot"},
    {"assurance": "entra"},
    {"client_id": "1158"},
    {"token_present": False},
])
def test_wrong_user_m365_admin_or_client_scoped_cannot_approve_jason(monkeypatch, changes):
    authenticated(monkeypatch, **changes)
    with pytest.raises(PermissionError, match="JASON_LICENSED_OWNER_REQUIRED"):
        server._authority_admin_owner()
    with pytest.raises(PermissionError, match="JASON_LICENSED_OWNER_REQUIRED"):
        server._component_approval_owner()
    with pytest.raises(PermissionError, match="JASON_LICENSED_OWNER_REQUIRED"):
        server._release_approval_owner()


def test_unknown_profile_denied(monkeypatch):
    authenticated(monkeypatch, profile="unknown")
    with pytest.raises(PermissionError, match="AUTHORITY_GRANT_ADMIN_POLICY_INVALID"):
        server._authority_admin_owner()


def test_legacy_profile_not_silently_switched_to_licensed_owner(monkeypatch):
    authenticated(monkeypatch, profile="")
    with pytest.raises(PermissionError, match="AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"):
        server._authority_admin_owner()


def test_new_profile_never_changes_microsoft_admin_identity(monkeypatch):
    authenticated(monkeypatch)
    assert server._licensed_jason_owner() == (LICENSED_PRINCIPAL, "aot")
    authenticated(monkeypatch, principal=M365_ADMIN_PRINCIPAL, oid=M365_ADMIN_OID)
    with pytest.raises(PermissionError, match="JASON_LICENSED_OWNER_REQUIRED"):
        server._licensed_jason_owner()


def test_jason_owner_can_record_one_exact_approval_required_grant(monkeypatch):
    from kernel.identity_authority import (
        IdentityRecord, InMemoryIdentityRepository,
        InMemoryAuthorityGrantRepository,
    )
    identities = InMemoryIdentityRepository()
    identities.put(IdentityRecord(LICENSED_PRINCIPAL, "human", "aot"))
    identities.put(IdentityRecord("test-recipient", "service", "aot"))
    grants = InMemoryAuthorityGrantRepository()
    events = []
    runtime = SimpleNamespace(
        identity_authority=SimpleNamespace(
            identities=identities, grants=grants,
            audit=SimpleNamespace(append_authority_audit=lambda **kw: events.append(kw)),
        ),
        capabilities=SimpleNamespace(list_all=lambda: (
            SimpleNamespace(
                capability_name="service.ticket.note.create",
                lifecycle_status=SimpleNamespace(value="active"),
            ),
        )),
    )
    monkeypatch.setattr(server, "_runtime", lambda: runtime)
    authenticated(monkeypatch)
    action = dict(
        subject_id="test-recipient", capability="service.ticket.note.create",
        permission="execute", approval_required=True, client_id="1158",
    )
    result = server.grant_exact_authority(**action)
    assert result["status"] == "succeeded"
    assert result["approval_required"] is True
    assert result["client_id"] == "1158"
    assert len(events) == 2
    assert server.grant_exact_authority(**action)["idempotent"] is True
    assert len(events) == 2
    # Entra administrative sign-in is not a Jason Owner authorization source.
    authenticated(monkeypatch, principal=M365_ADMIN_PRINCIPAL, oid=M365_ADMIN_OID)
    denied = server.grant_exact_authority(**{**action, "client_id": "1160"})
    assert denied["status"] == "rejected"
    assert denied["error_code"] == "JASON_LICENSED_OWNER_REQUIRED"
    assert len(grants.list_for_subject("test-recipient")) == 1
    assert len(events) == 2
