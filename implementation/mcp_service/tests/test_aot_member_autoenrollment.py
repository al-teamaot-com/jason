from types import SimpleNamespace

import pytest

from jason_mcp import server


TENANT = server.JASON_ENTRA_TENANT_ID
OID = "9f9fa80f-e756-4fe5-ace6-9bbd2e81d1ba"


class FakeDirectory:
    def __init__(self, user):
        self.user = dict(user)
        self.calls = []

    def read_user(self, *, microsoft_tenant_id, microsoft_object_id):
        self.calls.append((microsoft_tenant_id, microsoft_object_id))
        return dict(self.user)


class FakeIdentities:
    def __init__(self):
        self.records = {}

    def get(self, identity_id):
        return self.records.get(identity_id)

    def put(self, record):
        self.records[record.identity_id] = record


class FakeBindings:
    def __init__(self):
        self.records = {}

    def find(self, *, microsoft_tenant_id, microsoft_object_id):
        return self.records.get((microsoft_tenant_id, microsoft_object_id))

    def put(self, binding):
        self.records[(binding.microsoft_tenant_id, binding.microsoft_object_id)] = binding


def app_for(user):
    identities = FakeIdentities()
    directory = FakeDirectory(user)
    app = SimpleNamespace(
        microsoft_user_directory=directory,
        identity_authority=SimpleNamespace(identities=identities),
    )
    return app, identities, directory


def test_teamaot_member_autoenrolls_as_aot_human_without_individual_grants():
    app, identities, directory = app_for(
        {
            "id": OID,
            "mail": "Lori@TeamAOT.com",
            "userPrincipalName": "lori@teamaot.com",
            "accountEnabled": True,
        }
    )
    bindings = FakeBindings()

    binding = server._auto_enroll_aot_member(
        app=app,
        bindings=bindings,
        tenant_id=TENANT,
        object_id=OID,
    )

    assert binding.status == "active"
    assert binding.email_address == "lori@teamaot.com"
    assert binding.client_id is None
    identity = identities.get(binding.jason_identity_id)
    assert identity.identity_type == "human"
    assert identity.organization_id == "aot"
    assert identity.status == "active"
    assert directory.calls == [(TENANT, OID)]


def test_teamaom_member_is_eligible():
    app, _, _ = app_for(
        {
            "id": OID,
            "mail": "tech@teamaom.com",
            "userPrincipalName": "tech@teamaom.com",
            "accountEnabled": True,
        }
    )
    binding = server._auto_enroll_aot_member(
        app=app,
        bindings=FakeBindings(),
        tenant_id=TENANT,
        object_id=OID,
    )
    assert binding.email_address == "tech@teamaom.com"


def test_external_or_guest_upn_is_rejected_even_with_aot_mail_alias():
    app, identities, _ = app_for(
        {
            "id": OID,
            "mail": "contractor@teamaot.com",
            "userPrincipalName": "contractor_example.com#EXT#@aot.onmicrosoft.com",
            "accountEnabled": True,
        }
    )

    with pytest.raises(PermissionError, match="MCP_IDENTITY_DOMAIN_NOT_ALLOWED"):
        server._auto_enroll_aot_member(
            app=app,
            bindings=FakeBindings(),
            tenant_id=TENANT,
            object_id=OID,
        )
    assert identities.records == {}


def test_disabled_aot_account_is_rejected():
    app, identities, _ = app_for(
        {
            "id": OID,
            "mail": "lori@teamaot.com",
            "userPrincipalName": "lori@teamaot.com",
            "accountEnabled": False,
        }
    )

    with pytest.raises(PermissionError, match="MCP_IDENTITY_AUTOENROLL_ACCOUNT_DISABLED"):
        server._auto_enroll_aot_member(
            app=app,
            bindings=FakeBindings(),
            tenant_id=TENANT,
            object_id=OID,
        )
    assert identities.records == {}


def test_repeat_autoenrollment_is_idempotent_for_same_entra_object():
    app, identities, _ = app_for(
        {
            "id": OID,
            "mail": "lori@teamaot.com",
            "userPrincipalName": "lori@teamaot.com",
            "accountEnabled": True,
        }
    )
    bindings = FakeBindings()

    first = server._auto_enroll_aot_member(
        app=app, bindings=bindings, tenant_id=TENANT, object_id=OID
    )
    second = server._auto_enroll_aot_member(
        app=app, bindings=bindings, tenant_id=TENANT, object_id=OID
    )

    assert first.jason_identity_id == second.jason_identity_id
    assert len(identities.records) == 1
    assert len(bindings.records) == 1
