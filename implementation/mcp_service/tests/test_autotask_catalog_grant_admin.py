"""Fail-closed, isolated MCP authority tests; no provider, live grants, or secrets."""
from types import SimpleNamespace

import pytest

from jason_mcp import server
from jason_mcp.catalog_grant_admin import (
    CATALOG_CAPABILITIES, EXPECTED_OBJECT_ID, EXPECTED_PRINCIPAL,
    EXPECTED_TENANT_ID, PROFILE, PROFILE_ENV,
)
from kernel.identity_authority import (
    AuthorityGrant, IdentityRecord, InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository, PermissionMode,
)


class Audit:
    def __init__(self):
        self.events = []

    def append_authority_audit(self, **kwargs):
        self.events.append(kwargs)


class Capabilities:
    def list_all(self):
        all_names = (*sorted(CATALOG_CAPABILITIES), "service.ticket.update", "automation.component.schedule")
        return tuple(SimpleNamespace(
            capability_name=name, lifecycle_status=SimpleNamespace(value="active"),
        ) for name in all_names)


@pytest.fixture
def active(monkeypatch):
    identity = InMemoryIdentityRepository()
    for principal, org in (
        (EXPECTED_PRINCIPAL, "aot"),
        ("person-other-aot", "aot"),
        ("person-legacy-owner", "aot"),
        ("person-foreign", "other"),
    ):
        identity.put(IdentityRecord(
            identity_id=principal, identity_type="human", organization_id=org,
        ))
    app = SimpleNamespace(
        identity_authority=SimpleNamespace(
            identities=identity, grants=InMemoryAuthorityGrantRepository(), audit=Audit(),
        ), capabilities=Capabilities(),
    )
    monkeypatch.setattr(server, "_runtime", lambda: app)
    monkeypatch.setattr(server, "approval_owner_identities", lambda: frozenset({"person-legacy-owner"}))
    monkeypatch.setattr(server, "_authenticated_write_identity", lambda: (
        EXPECTED_PRINCIPAL, "aot", "entra-oauth-bearer", None,
    ))
    monkeypatch.setattr(server, "get_access_token", lambda: SimpleNamespace(claims={
        "tid": EXPECTED_TENANT_ID, "oid": EXPECTED_OBJECT_ID,
    }))
    monkeypatch.setenv(PROFILE_ENV, PROFILE)
    monkeypatch.delenv("JASON_AOT_ADMIN_APPROVER_PROFILE", raising=False)
    return app


def action(name="service.service.create", **kwargs):
    return dict(
        subject_id=EXPECTED_PRINCIPAL, capability=name,
        permission="execute", approval_required=True, client_id=None, **kwargs,
    )


@pytest.mark.parametrize("capability", sorted(CATALOG_CAPABILITIES))
def test_exact_four_catalog_grants_are_self_only_and_audited(active, capability):
    result = server.grant_exact_authority(**action(capability))
    assert result["status"] == "succeeded"
    assert result["subject_id"] == EXPECTED_PRINCIPAL
    assert result["capability"] == capability
    assert result["permission"] == "execute"
    assert result["approval_required"] is True
    assert result["client_id"] is None
    grant = active.identity_authority.grants.get(result["grant_id"])
    assert grant.subject_id == EXPECTED_PRINCIPAL
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.approval_required is True
    assert [entry["event_type"] for entry in active.identity_authority.audit.events] == [
        "authority.grant.create.requested", "authority.grant.created",
    ]
    assert all(entry["principal_id"] == EXPECTED_PRINCIPAL for entry in active.identity_authority.audit.events)
    assert all("CATALOG_SELF_GRANT_ADMIN" in entry["reason_codes"]
               for entry in active.identity_authority.audit.events)
    reread = server.list_exact_authority_grants()
    assert reread["status"] == "succeeded"
    assert [g["capability"] for g in reread["grants"]] == [capability]
    duplicate = server.grant_exact_authority(**action(capability))
    assert duplicate["status"] == "succeeded"
    assert duplicate["idempotent"] is True
    assert len(active.identity_authority.audit.events) == 2


@pytest.mark.parametrize("override", [
    {"subject_id": "person-other-aot"},
    {"subject_id": "person-legacy-owner"},
    {"capability": "service.ticket.update"},
    {"capability": "service.service.*"},
    {"capability": "service.product.update"},
    {"permission": "observe"},
    {"permission": "administer"},
    {"approval_required": False},
    {"client_id": "1158"},
    {"client_id": ""},
])
def test_catalog_fallback_denies_any_broader_grant(active, override):
    params = action()
    params.update(override)
    result = server.grant_exact_authority(**params)
    assert result["status"] == "rejected"
    assert result["error_code"] == "CATALOG_GRANT_ADMIN_SCOPE_DENIED"
    assert active.identity_authority.grants.list_for_subject(EXPECTED_PRINCIPAL) == ()
    assert active.identity_authority.audit.events == []


@pytest.mark.parametrize("identity,claim,profile,admin_mode", [
    ((EXPECTED_PRINCIPAL, "aot", "entra-oauth-bearer", "1158"), None, PROFILE, ""),
    ((EXPECTED_PRINCIPAL, "other", "entra-oauth-bearer", None), None, PROFILE, ""),
    ((EXPECTED_PRINCIPAL, "aot", "entra", None), None, PROFILE, ""),
    (("person-other-aot", "aot", "entra-oauth-bearer", None), None, PROFILE, ""),
    (None, {"tid": "00000000-0000-4000-8000-000000000000", "oid": EXPECTED_OBJECT_ID}, PROFILE, ""),
    (None, {"tid": EXPECTED_TENANT_ID, "oid": "00000000-0000-4000-8000-000000000000"}, PROFILE, ""),
    (None, {"tid": EXPECTED_TENANT_ID}, PROFILE, ""),
    (None, {"tid": EXPECTED_TENANT_ID, "oid": "invalid"}, PROFILE, ""),
    (None, None, "", ""),
    (None, None, "unknown", ""),
    (None, None, PROFILE, "admin-separated-v1"),
])
def test_wrong_identity_token_policy_or_mode_never_writes(active, monkeypatch, identity, claim, profile, admin_mode):
    if identity is not None:
        monkeypatch.setattr(server, "_authenticated_write_identity", lambda: identity)
    if claim is not None:
        monkeypatch.setattr(server, "get_access_token", lambda: SimpleNamespace(claims=claim))
    if profile != PROFILE:
        monkeypatch.setenv(PROFILE_ENV, profile)
    if admin_mode:
        monkeypatch.setenv("JASON_AOT_ADMIN_APPROVER_PROFILE", admin_mode)
        # The existing independently tested V4 Owner gate rejects this
        # regular principal. Simulate its authenticated rejection without
        # loading host-private V4 material in a source-only container.
        def denied_v4_owner():
            raise PermissionError("AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED")
        monkeypatch.setattr(server, "_authority_admin_owner", denied_v4_owner)
    result = server.grant_exact_authority(**action())
    assert result["status"] == "rejected"
    assert result["error_code"] in {
        "AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED",
        "CATALOG_GRANT_ADMIN_PROFILE_INVALID",
        "CATALOG_GRANT_ADMIN_POLICY_CONFLICT",
        "CATALOG_GRANT_ADMIN_IDENTITY_DENIED",
    }
    assert active.identity_authority.grants.list_for_subject(EXPECTED_PRINCIPAL) == ()
    assert active.identity_authority.audit.events == []


def test_unverified_missing_access_token_denied(active, monkeypatch):
    monkeypatch.setattr(server, "get_access_token", lambda: None)
    assert server.grant_exact_authority(**action())["error_code"] == "CATALOG_GRANT_ADMIN_IDENTITY_DENIED"
    assert active.identity_authority.audit.events == []


def test_catalog_listing_never_reveals_other_grants_or_other_subject(active):
    repo = active.identity_authority.grants
    repo.put(AuthorityGrant(
        grant_id="unrelated-ticket", subject_id=EXPECTED_PRINCIPAL,
        capability="service.ticket.update", organization_id="aot", client_id=None,
        permission=PermissionMode.EXECUTE, approval_required=True, status="active",
    ))
    repo.put(AuthorityGrant(
        grant_id="other-person", subject_id="person-other-aot",
        capability="service.service.create", organization_id="aot", client_id=None,
        permission=PermissionMode.EXECUTE, approval_required=True, status="active",
    ))
    result = server.list_exact_authority_grants(EXPECTED_PRINCIPAL)
    assert result["status"] == "succeeded" and result["grants"] == []
    assert server.list_exact_authority_grants("person-other-aot")["error_code"] == "CATALOG_GRANT_ADMIN_SCOPE_DENIED"
    assert active.identity_authority.audit.events == []


def test_exact_owned_catalog_grant_can_be_revoked_but_not_other_grants(active):
    added = server.grant_exact_authority(**action())
    denied = server.revoke_exact_authority_grant("unrelated-ticket")
    assert denied["status"] == "rejected"
    grant = active.identity_authority.grants.get(added["grant_id"])
    assert grant.status == "active"
    result = server.revoke_exact_authority_grant(added["grant_id"])
    assert result["status"] == "succeeded"
    assert result["status_after"] == "revoked"
    assert active.identity_authority.grants.get(added["grant_id"]).status == "revoked"


def test_revoke_rejects_cross_principal_and_non_catalog(active):
    repo = active.identity_authority.grants
    for grant in (
        AuthorityGrant(grant_id="other-owned-catalog", subject_id="person-other-aot",
            capability="service.service.create", organization_id="aot", client_id=None,
            permission=PermissionMode.EXECUTE, approval_required=True),
        AuthorityGrant(grant_id="own-ticket", subject_id=EXPECTED_PRINCIPAL,
            capability="service.ticket.update", organization_id="aot", client_id=None,
            permission=PermissionMode.EXECUTE, approval_required=True),
        AuthorityGrant(grant_id="own-catalog-noapproval", subject_id=EXPECTED_PRINCIPAL,
            capability="service.service.create", organization_id="aot", client_id=None,
            permission=PermissionMode.EXECUTE, approval_required=False),
    ):
        repo.put(grant)
    for grant_id in ("other-owned-catalog", "own-ticket", "own-catalog-noapproval"):
        assert server.revoke_exact_authority_grant(grant_id)["error_code"] == "CATALOG_GRANT_ADMIN_SCOPE_DENIED"
        assert repo.get(grant_id).status == "active"
    assert active.identity_authority.audit.events == []


def test_disabled_profile_prevents_catalog_list_and_revoke(active, monkeypatch):
    result = server.grant_exact_authority(**action())
    monkeypatch.delenv(PROFILE_ENV)
    assert server.list_exact_authority_grants()["error_code"] == "AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"
    assert server.revoke_exact_authority_grant(result["grant_id"])["error_code"] == "AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"


def test_no_global_owner_or_unrelated_admin_rights(active):
    # New authority is never reflected in the shared global Owner allowlist.
    assert EXPECTED_PRINCIPAL not in server.approval_owner_identities()
    # Independently authenticated licensed Owner may view canary status,
    # but still cannot administer its grants or execute it.
    assert server.provider_health_canary_status()["status"] == "succeeded"
    assert server.grant_exact_authority(**action("service.ticket.update"))["status"] == "rejected"
    assert active.identity_authority.audit.events == []


def test_inactive_owner_subject_cannot_use_catalog_grant_admin(active):
    active.identity_authority.identities.put(IdentityRecord(
        identity_id=EXPECTED_PRINCIPAL, identity_type="human", organization_id="aot", status="disabled",
    ))
    result = server.grant_exact_authority(**action())
    assert result["status"] == "rejected"
    assert result["error_code"] == "AUTHORITY_GRANT_ACTIVE_SUBJECT_REQUIRED"
    assert active.identity_authority.grants.list_for_subject(EXPECTED_PRINCIPAL) == ()


def test_unregistered_or_disabled_catalog_capability_cannot_be_granted(active):
    active.capabilities.list_all = lambda: (
        SimpleNamespace(capability_name="service.service.create",
                        lifecycle_status=SimpleNamespace(value="building")),
    )
    result = server.grant_exact_authority(**action())
    assert result["status"] == "rejected"
    assert result["error_code"] == "AUTHORITY_GRANT_ACTIVE_CAPABILITY_REQUIRED"
    assert active.identity_authority.audit.events == []
    assert active.identity_authority.grants.list_for_subject(EXPECTED_PRINCIPAL) == ()


def test_audit_unavailable_prevents_creating_grant(active):
    active.identity_authority.audit = None
    result = server.grant_exact_authority(**action())
    assert result["status"] == "rejected"
    assert result["error_code"] == "AUTHORITY_GRANT_AUDIT_UNAVAILABLE"
    assert active.identity_authority.grants.list_for_subject(EXPECTED_PRINCIPAL) == ()


def test_unrelated_owner_only_approval_guard_is_unchanged(active):
    with pytest.raises(PermissionError, match="DATTO_COMPONENT_APPROVAL_OWNER_REQUIRED"):
        server._component_approval_owner()
    with pytest.raises(PermissionError, match="AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"):
        server._authority_admin_owner()
