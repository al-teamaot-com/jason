from types import SimpleNamespace

import pytest
from kernel.identity_authority import AuthorityOutcome

from connectors.constant_contact.import_activity import build_specification
from connectors.constant_contact.import_preflight import preflight
from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.import_work_store import EncryptedImportWorkStore
from jason_runtime.constant_contact_import_workflow import ConstantContactImportWorkflow

LIST_ID = "11111111-2222-3333-4444-555555555555"


def spec():
    preview = preflight([{
        "email": "one@example.com",
        "marketing_consent": "explicit",
        "consent_evidence": "verified opt-in receipt",
    }])
    return build_specification(preview, list_ids=[LIST_ID])


class Bindings:
    def __init__(self):
        self.allowed = True
    def find(self, *, microsoft_tenant_id, microsoft_object_id):
        if not self.allowed:
            return None
        assert microsoft_tenant_id == "tenant"
        assert microsoft_object_id == "person"
        return SimpleNamespace(status="active", jason_identity_id="aot-owner")


class Authority:
    def __init__(self):
        self.allow = True
        self.identities = SimpleNamespace(get=lambda x: SimpleNamespace(
            status="active", organization_id="aot",
        ))
        self.calls = []
    def evaluate(self, request):
        self.calls.append(request)
        assert request.capability == "marketing.contact.search"
        assert request.organization_id == "aot"
        assert request.requested_mode.value == "observe"
        return SimpleNamespace(
            outcome=AuthorityOutcome.ALLOWED if self.allow else AuthorityOutcome.DENIED,
        )


class Issuer:
    def __init__(self):
        self.bindings = Bindings()
        self.authority = Authority()
        self.called = []
    def submit_plan(self, **kw):
        self.called.append(kw)
        original = kw["requests"][0]
        assert original.capability_name == "marketing.contact.import"
        assert original.organization_id == "aot"
        assert original.principal_id == "aot-owner"
        assert original.permission_mode == "execute"
        assert original.approval_present is False
        assert original.authority_allowed is False
        assert original.arguments["contact_count"] == 1
        assert original.arguments["list_ids"] == [LIST_ID]
        assert "email" not in original.arguments
        assert "access_token" not in original.arguments
        assert kw["production"] is True
        return {
            "approval_id": "planapproval-signed-from-existing-issuer",
            "plan_fingerprint": "f" * 64,
            "status": "awaiting_approval",
        }


class Connector:
    def __init__(self, work_store):
        self.work_store = work_store
        self.requesters = []
    def create_preview(self, *, requester_id, workbook, list_ids):
        self.requesters.append(requester_id)
        return self.work_store.create(
            requester_id=requester_id,
            specification=spec(),
            account_binding_sha256="a" * 64,
            suppression_receipt_sha256="b" * 64,
        )
    def reconcile(self, *, work_id, requester_id):
        self.work_store.load_for_reconciliation(
            work_id=work_id, requester_id=requester_id,
        )
        return {"status": "pending_or_unknown", "work_id": work_id}


def setup(tmp_path):
    store = EncryptedImportWorkStore(tmp_path / "work.db", b"k" * 32)
    issuer = Issuer()
    connector = Connector(store)
    workflow = ConstantContactImportWorkflow(connector, store, issuer)
    identity = SimpleNamespace(
        authentication_assurance="botframework-authenticated",
        microsoft_tenant_id="tenant", microsoft_object_id="person",
    )
    return workflow, identity, issuer, connector, store


def test_preview_exact_one_plan_no_raw_contacts_or_duplicate_approval(tmp_path):
    workflow, identity, issuer, connector, store = setup(tmp_path)
    work = workflow.preview(identity=identity, workbook=b"mock", list_ids=(LIST_ID,))
    assert connector.requesters == ["aot-owner"]
    result = workflow.submit_approval(identity=identity, work_id=work.work_id)
    assert result["status"] == "awaiting_approval"
    assert result["plan_fingerprint"] == "f" * 64
    bound = store.load_for_requester(work_id=work.work_id, requester_id="aot-owner")
    assert bound.approval_id == result["approval_id"]
    assert len(issuer.called) == 1
    with pytest.raises(ImportAuthorizationError, match="already"):
        workflow.submit_approval(identity=identity, work_id=work.work_id)
    assert len(issuer.called) == 1
    assert workflow.readback(identity=identity, work_id=work.work_id)["status"] == "pending_or_unknown"


def test_unbound_or_weak_requester_fails_before_any_provider_work(tmp_path):
    workflow, identity, issuer, connector, store = setup(tmp_path)
    identity.authentication_assurance = "unverified"
    with pytest.raises(ImportAuthorizationError, match="Authenticated"):
        workflow.preview(identity=identity, workbook=b"mock", list_ids=(LIST_ID,))
    assert not connector.requesters
    identity.authentication_assurance = "botframework-authenticated"
    issuer.bindings.allowed = False
    with pytest.raises(ImportAuthorizationError, match="binding"):
        workflow.preview(identity=identity, workbook=b"mock", list_ids=(LIST_ID,))
    assert not connector.requesters


def test_work_from_another_requester_cannot_approve_or_readback(tmp_path):
    workflow, identity, issuer, connector, store = setup(tmp_path)
    work = store.create(
        requester_id="another-user", specification=spec(),
        account_binding_sha256="a" * 64, suppression_receipt_sha256="b" * 64,
    )
    with pytest.raises(ImportAuthorizationError, match="owner"):
        workflow.submit_approval(identity=identity, work_id=work.work_id)
    assert not issuer.called
    with pytest.raises(ImportAuthorizationError, match="owner"):
        workflow.readback(identity=identity, work_id=work.work_id)



def test_authenticated_requester_without_read_permission_does_not_contact_provider(tmp_path):
    workflow, identity, issuer, connector, store = setup(tmp_path)
    issuer.authority.allow = False
    with pytest.raises(ImportAuthorizationError, match="contact-read permission"):
        workflow.preview(identity=identity, workbook=b"mock", list_ids=(LIST_ID,))
    assert connector.requesters == []
    assert len(issuer.authority.calls) == 1
