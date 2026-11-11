"""Network-isolated import path tests: real AES work and claim stores, fake provider."""
from io import BytesIO

import pytest

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext, ConnectorRequest
from connectors.constant_contact.governed_import import (
    GovernedConstantContactImportConnector, CAPABILITY,
    canonical_import_arguments,
)
from connectors.constant_contact.import_authorization import ImportAuthorizationError
from connectors.constant_contact.import_ledger import SQLiteImportActivityLedger
from connectors.constant_contact.import_work_store import EncryptedImportWorkStore

LIST_ID = "11111111-2222-3333-4444-555555555555"
ACTIVITY = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ACCOUNT = "aot1234567890"
APPROVAL_ID = "planapproval-isolated-test"


def workbook():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["email", "marketing_consent", "consent_evidence", "first_name"])
    ws.append(["one@example.com", "explicit", "2026-11-11 consent receipt", "One"])
    data = BytesIO()
    wb.save(data)
    return data.getvalue()


class Provider:
    def __init__(self):
        self.calls = []
        self.account = ACCOUNT
        self.permission = "explicit"
        self.exists = False
        self.memberships = []
        self.activity_counts = True
        self.fail_post = False
        self.saved_fields = {}
        self.drop_metadata = False

    def request(self, **kw):
        self.calls.append(kw)
        path, method = kw["url"], kw["method"]
        if method == "GET":
            if path.endswith("/account/summary"):
                return {"encoded_account_id": self.account}
            if path.endswith("/contact_lists/" + LIST_ID):
                return {"list_id": LIST_ID, "name": "AOT Test List"}
            if path.endswith("/contacts"):
                email = kw["params"]["email"]
                assert kw["params"]["status"] == "all"
                return {
                    "_links": {},
                    "contacts": ([{
                        "email_address": {
                            "address": email,
                            "permission_to_send": self.permission,
                        },
                        "list_memberships": list(self.memberships),
                        **({} if self.drop_metadata else dict(self.saved_fields)),
                    }] if self.exists else []),
                }
            if path.endswith("/activities/" + ACTIVITY):
                value = {
                    "activity_id": ACTIVITY, "state": "completed",
                    "percent_done": 100, "activity_errors": [],
                    "completed_at": "2026-11-11T20:00:00Z",
                }
                if self.activity_counts:
                    value["status"] = {
                        "items_total_count": 1, "items_completed_count": 1,
                        "error_count": 0, "cannot_add_to_list_count": 0,
                    }
                return value
            raise AssertionError("Unexpected GET")
        assert method == "POST"
        assert path.endswith("/activities/contacts_json_import")
        assert kw["json"]["import_data"][0]["email"] == "one@example.com"
        if self.fail_post:
            raise ConnectionError("simulated ambiguous POST response")
        self.saved_fields = {
            key: value for key, value in kw["json"]["import_data"][0].items()
            if key != "email"
        }
        self.exists = True
        self.memberships = [LIST_ID]
        return {"activity_id": ACTIVITY, "state": "initialized"}


class Approval:
    def __init__(self, reject=False):
        self.reject = reject
        self.calls = []

    def require_exact_signed_approval(self, *, requester_id, intent):
        self.calls.append((requester_id, intent.digest()))
        if self.reject:
            raise ImportAuthorizationError("No verified exact-action grant")


def make_service(tmp_path, *, enabled=True, approved=True):
    transport = Provider()
    claims = SQLiteImportActivityLedger(tmp_path / "claims.sqlite3")
    store = EncryptedImportWorkStore(tmp_path / "work.sqlite3", b"A" * 32)
    approval = Approval(reject=not approved)
    engine = GovernedConstantContactImportConnector(
        transport=transport, session=lambda: ("token-for-isolated-test", ACCOUNT),
        work_store=store, claims=claims, approvals=lambda work: approval,
        execute_enabled=enabled, min_read_interval_seconds=0,
    )
    return engine, transport, store, claims, approval


def make_request(work, *, principal="aot-technician", organization="aot"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="test-correlation", principal_id=principal,
            organization_id=organization, client_id=None,
            capability=CAPABILITY, mode="execute",
        ),
        arguments=canonical_import_arguments(work),
    )


def prepare_work(engine, store):
    preview = engine.create_preview(
        requester_id="aot-technician", workbook=workbook(),
        list_ids=(LIST_ID,),
    )
    return store.attach_approval(
        work_id=preview.work_id,
        requester_id="aot-technician",
        approval_id=APPROVAL_ID,
    )


def post_count(transport):
    return sum(call["method"] == "POST" for call in transport.calls)


def test_end_to_end_one_time_dispatch_and_itemized_provider_readback(tmp_path):
    engine, transport, store, claims, approval = make_service(tmp_path)
    work = prepare_work(engine, store)
    assert b"one@example.com" not in (tmp_path / "work.sqlite3").read_bytes()
    req = make_request(work)
    first_plan = engine.prepare_governed_execution(req)
    second_plan = engine.prepare_governed_execution(req)
    assert first_plan.payload == second_plan.payload
    assert "email" not in repr(first_plan)
    assert post_count(transport) == 0
    result = engine.execute_governed_execution(second_plan)
    assert result.data["status"] == "pending_unverified"
    assert post_count(transport) == 1
    done = engine.reconcile(
        work_id=work.work_id, requester_id="aot-technician",
    )
    assert done["status"] == "verified"
    assert done["verified_count"] == 1
    assert len(done["per_record"][0]["email_sha256"]) == 64
    assert done["per_record"][0]["status"] == "verified"
    assert claims.read_verification(
        intent_digest=canonical_import_arguments(work)["intent_digest"],
    )
    # A repeated approved request cannot post a second activity.
    with pytest.raises(ImportAuthorizationError):
        engine.execute_governed_execution(second_plan)
    assert post_count(transport) == 1


@pytest.mark.parametrize("enabled,approved,expected", [
    (False, True, "not activated"),
    (True, False, "exact-action grant"),
])
def test_disabled_or_denied_write_never_calls_post(tmp_path, enabled, approved, expected):
    engine, transport, store, _, _ = make_service(
        tmp_path, enabled=enabled, approved=approved,
    )
    work = prepare_work(engine, store)
    with pytest.raises((ConnectorAuthorizationError, ImportAuthorizationError), match=expected):
        engine.prepare_governed_execution(make_request(work))
    assert post_count(transport) == 0


def test_account_or_suppression_change_before_dispatch_blocks(tmp_path):
    engine, transport, store, _, _ = make_service(tmp_path)
    work = prepare_work(engine, store)
    transport.exists = True
    transport.permission = "unsubscribed"
    with pytest.raises(ImportAuthorizationError, match="suppressed"):
        engine.prepare_governed_execution(make_request(work))
    assert post_count(transport) == 0


def test_wrong_requester_is_rejected_before_provider_reads(tmp_path):
    engine, transport, store, _, _ = make_service(tmp_path)
    work = prepare_work(engine, store)
    count = len(transport.calls)
    with pytest.raises(ImportAuthorizationError, match="owner"):
        engine.prepare_governed_execution(make_request(work, principal="intruder"))
    assert len(transport.calls) == count


def test_unknown_activity_response_never_redispatches_after_restart(tmp_path):
    engine, transport, store, claims, _ = make_service(tmp_path)
    work = prepare_work(engine, store)
    prepared = engine.prepare_governed_execution(make_request(work))
    transport.fail_post = True
    with pytest.raises(ConnectionError):
        engine.execute_governed_execution(prepared)
    assert post_count(transport) == 1
    assert engine.reconcile(work_id=work.work_id, requester_id="aot-technician")["status"] == "pending_or_unknown"
    with pytest.raises(ImportAuthorizationError, match="already claimed"):
        engine.execute_governed_execution(prepared)
    assert post_count(transport) == 1


def test_missing_activity_counts_or_list_membership_does_not_claim_success(tmp_path):
    engine, transport, store, claims, _ = make_service(tmp_path)
    work = prepare_work(engine, store)
    prepared = engine.prepare_governed_execution(make_request(work))
    engine.execute_governed_execution(prepared)
    transport.activity_counts = False
    assert engine.reconcile(work_id=work.work_id, requester_id="aot-technician")["status"] == "provider_counts_unverified"
    transport.activity_counts = True
    transport.memberships = []
    assert engine.reconcile(work_id=work.work_id, requester_id="aot-technician")["status"] == "incomplete_provider_readback"
    digest = canonical_import_arguments(work)["intent_digest"]
    assert claims.read_verification(intent_digest=digest) is None


def test_native_connector_execution_plan_is_secret_free_and_non_bypassable(tmp_path):
    """Import uses Jason's provider binding, never read-only/direct invoke."""
    from decimal import Decimal
    from types import SimpleNamespace
    from connectors.core.contracts import ConnectorAuthorizationError
    from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
    from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
    from orchestrator.contracts import OrchestrationMode, OrchestrationRequest

    engine, transport, store, claims, approval = make_service(tmp_path)
    work = prepare_work(engine, store)
    bound = GovernedConnectorCapabilityInvoker(
        connectors={"constant_contact": engine},
        provider_capability_map={
            ("constant_contact", CAPABILITY): CAPABILITY,
        },
    )
    request = OrchestrationRequest(
        execution_id="import-exec", correlation_id="import-correlation",
        principal_id="aot-technician", organization_id="aot",
        capability_name=CAPABILITY, capability_version="1.0",
        requested_mode="deterministic", orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True, approval_present=True,
        risk="high", data_handling=DataHandlingPolicy("confidential", False),
        budget=ExecutionBudget(Decimal("0")),
        arguments=canonical_import_arguments(work),
        permission_mode="execute",
        authority_context_id="authorized-context",
        approval_id="trusted-governed-planstep",
    )
    resolution = SimpleNamespace(
        selected_provider_id="constant_contact", capability_name=CAPABILITY,
        metadata={},
    )
    with pytest.raises(ConnectorAuthorizationError, match="prepared execution plan"):
        bound.invoke(request=request, resolution=resolution)
    assert post_count(transport) == 0
    prepared_a = bound.prepare_execution_plan(request=request, resolution=resolution)
    prepared_b = bound.prepare_execution_plan(request=request, resolution=resolution)
    assert prepared_a.plan.fingerprint == prepared_b.plan.fingerprint
    assert prepared_a.plan.action_method == "POST"
    assert prepared_a.plan.resource_identifier == work.account_binding_sha256
    assert prepared_a.plan.normalized_path == "/v3/activities/contacts_json_import"
    assert "one@example.com" not in str(prepared_a.plan.canonical_material())
    assert "token-for-isolated-test" not in str(prepared_a.plan.canonical_material())
    result = bound.invoke_execution_plan(
        request=request, resolution=resolution, prepared=prepared_b,
    )
    assert result.output["data"]["status"] == "pending_unverified"
    assert result.attempts == 1
    assert post_count(transport) == 1



def test_provider_readback_rejects_missing_imported_fields(tmp_path):
    engine, transport, store, claims, approval = make_service(tmp_path)
    work = prepare_work(engine, store)
    prepared = engine.prepare_governed_execution(make_request(work))
    engine.execute_governed_execution(prepared)
    transport.drop_metadata = True
    result = engine.reconcile(
        work_id=work.work_id, requester_id="aot-technician",
    )
    assert result["status"] == "incomplete_provider_readback"
    assert result["per_record"][0]["status"] == "not_verified"
    assert claims.read_verification(
        intent_digest=canonical_import_arguments(work)["intent_digest"],
    ) is None
