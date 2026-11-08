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
            SimpleNamespace(capability_name="service.ticket.client.notification.create", lifecycle_status=SimpleNamespace(value="active")),
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


# Privileged role is a separate, explicitly sourced V4 policy, not a
# migration of the admin login to the ordinary technician/Owner binding.
ADMIN_TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
ADMIN_OID = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
NORMAL_OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ADMIN_PRINCIPAL = "person-entra-c848022de13b445784b0e2f5c00dcaf6"
NORMAL_PRINCIPAL = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"


def v4_admin_fixture(monkeypatch, tmp_path, *, tenant=ADMIN_TENANT,
                     oid=ADMIN_OID, principal=ADMIN_PRINCIPAL,
                     client_id=None, enable=True):
    import json
    from pathlib import Path
    p=tmp_path / "root-owned-equivalent-v4.json"
    repo=Path(__file__).resolve().parents[3]
    source=repo / "config" / "mobile-release-approval-policy.json"
    policy=json.loads(source.read_text())
    assert policy["schema_version"] == "4.0"
    p.write_text(json.dumps(policy))
    p.chmod(0o600)
    runtime=app()
    runtime.identity_authority.identities.put(IdentityRecord(
        identity_id=ADMIN_PRINCIPAL, identity_type="human", organization_id="aot",
    ))
    runtime.identity_authority.identities.put(IdentityRecord(
        identity_id=NORMAL_PRINCIPAL, identity_type="human", organization_id="aot",
    ))
    monkeypatch.setattr(server,"_runtime",lambda:runtime)
    monkeypatch.setattr(
        server,"_authenticated_write_identity",
        lambda:(principal,"aot","entra-oauth-bearer",client_id),
    )
    monkeypatch.setattr(
        server,"get_access_token",
        lambda:SimpleNamespace(claims={"tid":tenant,"oid":oid}),
    )
    monkeypatch.setattr(server,"approval_owner_identities",lambda:frozenset({"person-al"}))
    monkeypatch.setenv("JASON_RELEASE_MOBILE_APPROVAL_POLICY",str(p))
    if enable:
        monkeypatch.setenv("JASON_AOT_ADMIN_APPROVER_PROFILE","admin-separated-v1")
    else:
        monkeypatch.delenv("JASON_AOT_ADMIN_APPROVER_PROFILE",raising=False)
    return runtime,p


def test_v4_authenticated_admin_can_add_one_approved_client_scoped_grant(monkeypatch, tmp_path):
    runtime,_=v4_admin_fixture(monkeypatch,tmp_path)
    # Recipient and action remain the normal identity, never elevated to
    # unrestricted Owner or admin account.
    action=server.grant_exact_authority(
        subject_id=NORMAL_PRINCIPAL,
        capability="service.ticket.client.notification.create",
        permission="execute",approval_required=True,client_id="1158",
    )
    assert action["status"]=="succeeded"
    assert action["client_id"]=="1158"
    assert action["subject_id"]==NORMAL_PRINCIPAL
    assert action["approval_required"] is True
    grant=runtime.identity_authority.grants.get(action["grant_id"])
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.subject_id==NORMAL_PRINCIPAL
    assert grant.client_id=="1158"
    assert grant.approval_required is True
    reread=server.list_exact_authority_grants(subject_id=NORMAL_PRINCIPAL)
    assert reread["status"]=="succeeded"
    assert len(reread["grants"])==1
    assert reread["grants"][0]["grant_id"]==action["grant_id"]
    retry=server.grant_exact_authority(
        subject_id=NORMAL_PRINCIPAL,
        capability="service.ticket.client.notification.create",
        permission="execute",approval_required=True,client_id="1158",
    )
    assert retry["status"]=="succeeded" and retry["idempotent"] is True
    assert len(runtime.identity_authority.audit.events)==2


@pytest.mark.parametrize("tenant,oid,principal,client",[
    (ADMIN_TENANT,NORMAL_OID,NORMAL_PRINCIPAL,None),
    (ADMIN_TENANT,NORMAL_OID,ADMIN_PRINCIPAL,None),
    (ADMIN_TENANT,ADMIN_OID,NORMAL_PRINCIPAL,None),
    ("00000000-0000-4000-8000-000000000000",ADMIN_OID,ADMIN_PRINCIPAL,None),
    (ADMIN_TENANT,ADMIN_OID,ADMIN_PRINCIPAL,"1158"),
    (ADMIN_TENANT,"00000000-0000-4000-8000-000000000000",ADMIN_PRINCIPAL,None),
])
def test_v4_regular_wrong_tenant_wrong_id_and_client_scope_never_administer(
        monkeypatch,tmp_path,tenant,oid,principal,client):
    runtime,_=v4_admin_fixture(
        monkeypatch,tmp_path,tenant=tenant,oid=oid,principal=principal,
        client_id=client,
    )
    result=server.grant_exact_authority(
        subject_id=NORMAL_PRINCIPAL,capability="service.ticket.update",
        permission="execute",approval_required=True,client_id="1158",
    )
    assert result=={"status":"rejected","error_code":"AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"}
    assert server.list_exact_authority_grants(
        subject_id=NORMAL_PRINCIPAL
    )=={"status":"rejected","error_code":"AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"}
    assert not runtime.identity_authority.grants.list_for_subject(NORMAL_PRINCIPAL)


def test_v4_mode_not_active_on_legacy_source_or_off_profile(monkeypatch,tmp_path):
    from implementation.runtime_service.tests.test_mobile_release_approval import (
        reviewed_policy_file,
    )
    runtime,p=v4_admin_fixture(monkeypatch,tmp_path)
    policy=reviewed_policy_file(tmp_path)
    monkeypatch.setenv("JASON_RELEASE_MOBILE_APPROVAL_POLICY",str(policy))
    result=server.grant_exact_authority(
        subject_id=NORMAL_PRINCIPAL,capability="service.ticket.update",
        permission="execute",approval_required=True,
    )
    assert result=={"status":"rejected","error_code":"AUTHORITY_GRANT_ADMIN_ROLE_POLICY_REQUIRED"}
    monkeypatch.setenv("JASON_RELEASE_MOBILE_APPROVAL_POLICY",str(p))
    monkeypatch.delenv("JASON_AOT_ADMIN_APPROVER_PROFILE",raising=False)
    assert server.list_exact_authority_grants(
        subject_id=NORMAL_PRINCIPAL
    )=={"status":"rejected","error_code":"AUTHORITY_GRANT_ADMIN_OWNER_REQUIRED"}
    assert not runtime.identity_authority.grants.list_for_subject(NORMAL_PRINCIPAL)


@pytest.mark.parametrize("permission,approve,client,capability",[
    ("execute",False,"1158","service.ticket.update"),
    ("administer",True,"1158","service.ticket.update"),
    ("execute",True,"*","service.ticket.update"),
    ("execute",True,"1158","service.*"),
])
def test_v4_privileged_admin_cannot_issue_unsafe_exact_grant(
        monkeypatch,tmp_path,permission,approve,client,capability):
    runtime,_=v4_admin_fixture(monkeypatch,tmp_path)
    result=server.grant_exact_authority(
        subject_id=NORMAL_PRINCIPAL,capability=capability,
        permission=permission,approval_required=approve,client_id=client,
    )
    assert result["status"]=="rejected"
    assert not runtime.identity_authority.grants.list_for_subject(NORMAL_PRINCIPAL)
