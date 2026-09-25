from types import SimpleNamespace

import pytest

from jason_mcp import server
from kernel.identity_authority import (
    AuthorityGrant,
    IdentityRecord,
    InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository,
    PermissionMode,
)


class Audit:
    def __init__(self): self.events=[]
    def append_authority_audit(self, **kwargs): self.events.append(kwargs)


class CapabilityRegistry:
    def __init__(self):
        self.items=[
            SimpleNamespace(capability_name="service.ticket.attachment.create", lifecycle_status=SimpleNamespace(value="active")),
            SimpleNamespace(capability_name="service.ticket.update", lifecycle_status=SimpleNamespace(value="active")),
        ]
    def list_all(self): return tuple(self.items)


def app():
    identities=InMemoryIdentityRepository()
    identities.put(IdentityRecord(identity_id="person-al",identity_type="human",organization_id="aot"))
    identities.put(IdentityRecord(identity_id="person-tech",identity_type="human",organization_id="aot"))
    identities.put(IdentityRecord(identity_id="person-other",identity_type="human",organization_id="other"))
    authority=SimpleNamespace(
        identities=identities,
        grants=InMemoryAuthorityGrantRepository(),
        audit=Audit(),
    )
    return SimpleNamespace(identity_authority=authority, capabilities=CapabilityRegistry())


@pytest.fixture
def owner(monkeypatch):
    runtime=app()
    monkeypatch.setattr(server,"_runtime",lambda:runtime)
    monkeypatch.setattr(server,"_authenticated_write_identity",lambda:("person-al","aot","entra",None))
    monkeypatch.setattr(server,"approval_owner_identities",lambda:frozenset({"person-al"}))
    return runtime


def test_owner_can_add_exact_execute_grant_with_required_approval(owner):
    result=server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.attachment.create",
        permission="execute",approval_required=True,
    )
    assert result["status"] == "succeeded"
    assert result["idempotent"] is False
    grant=owner.identity_authority.grants.get(result["grant_id"])
    assert grant is not None
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.approval_required is True
    assert grant.client_id is None
    assert [e["event_type"] for e in owner.identity_authority.audit.events] == [
        "authority.grant.create.requested","authority.grant.created"
    ]


def test_exact_replay_is_idempotent_and_does_not_duplicate_audit(owner):
    first=server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.attachment.create",
        permission="execute",approval_required=True,
    )
    count=len(owner.identity_authority.audit.events)
    second=server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.attachment.create",
        permission="execute",approval_required=True,
    )
    assert second["status"] == "succeeded" and second["idempotent"] is True
    assert second["grant_id"] == first["grant_id"]
    assert len(owner.identity_authority.audit.events) == count


@pytest.mark.parametrize("capability",["service.*","service.ticket.?","[service.ticket.update]"])
def test_wildcard_capabilities_are_rejected(owner,capability):
    result=server.grant_exact_authority(
        subject_id="person-al",capability=capability,permission="execute",approval_required=True
    )
    assert result == {"status":"rejected","error_code":"AUTHORITY_GRANT_EXACT_CAPABILITY_REQUIRED"}


def test_non_active_or_unknown_capability_is_rejected(owner):
    result=server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.missing",permission="execute",approval_required=True
    )
    assert result["error_code"] == "AUTHORITY_GRANT_ACTIVE_CAPABILITY_REQUIRED"


def test_execute_without_approval_is_rejected(owner):
    result=server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.attachment.create",
        permission="execute",approval_required=False,
    )
    assert result["error_code"] == "AUTHORITY_GRANT_EXECUTE_REQUIRES_APPROVAL"


def test_administer_grant_is_rejected(owner):
    result=server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.attachment.create",
        permission="administer",approval_required=True,
    )
    assert result["error_code"] == "AUTHORITY_GRANT_ADMINISTER_NOT_ALLOWED"


def test_cross_org_subject_is_rejected(owner):
    result=server.grant_exact_authority(
        subject_id="person-other",capability="service.ticket.attachment.create",
        permission="execute",approval_required=True,
    )
    assert result["error_code"] == "AUTHORITY_GRANT_SUBJECT_ORGANIZATION_MISMATCH"


def test_non_owner_is_rejected(monkeypatch):
    runtime=app()
    monkeypatch.setattr(server,"_runtime",lambda:runtime)
    monkeypatch.setattr(server,"_authenticated_write_identity",lambda:("person-tech","aot","entra",None))
    monkeypatch.setattr(server,"approval_owner_identities",lambda:frozenset({"person-al"}))
    result=server.grant_exact_authority(
        subject_id="person-tech",capability="service.ticket.attachment.create",
        permission="execute",approval_required=True,
    )
    assert result["error_code"] == "AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"


def test_revoke_exact_grant_changes_status_and_audits(owner):
    created=server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.attachment.create",
        permission="execute",approval_required=True,
    )
    result=server.revoke_exact_authority_grant(created["grant_id"])
    assert result["status"] == "succeeded"
    assert result["status_after"] == "revoked"
    assert owner.identity_authority.grants.get(created["grant_id"]).status == "revoked"
    events=[e["event_type"] for e in owner.identity_authority.audit.events]
    assert events[-2:] == ["authority.grant.revoke.requested","authority.grant.revoked"]


def test_list_exact_grants_defaults_to_owner_subject(owner):
    server.grant_exact_authority(
        subject_id="person-al",capability="service.ticket.attachment.create",
        permission="execute",approval_required=True,
    )
    result=server.list_exact_authority_grants()
    assert result["status"] == "succeeded"
    assert result["subject_id"] == "person-al"
    assert len(result["grants"]) == 1
    assert result["grants"][0]["capability"] == "service.ticket.attachment.create"
