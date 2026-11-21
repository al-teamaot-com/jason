"""Full component through canonical issuer, Ed25519, live JKD and Root claims.

Only the external Teams delivery and native documentation side effects are
substituted. No production/secret files are mounted or customer calls made.
"""
import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from jason_openclaw.signed_transport import canonical_signed_payload
from jason_runtime.owner_objective_service import build
from jason_runtime.owner_objective_capabilities import CAPABILITIES, TEST_CAPABILITY
from kernel.identity_authority import (AuthorityGrant, IdentityRecord, PermissionMode,
    SQLiteAuthorityGrantRepository, SQLiteIdentityAuthorityStore, SQLiteIdentityRepository)
from orchestrator.approval_delivery import ApprovalDeliveryReceipt
from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore
from orchestrator.teams_plan_request_repository import request_material, scope_material
from tools.pmv4_teams_objective_admission import TENANT, LICENSED_OWNER, plan_digest
from tools.pmv4_teams_objective_store import RootObjectiveStore

NOW = datetime(2026, 11, 21, 6, 0, tzinfo=timezone.utc)
OWNER = "licensed-owner"
SERVICE = "jason-autonomy-worker"


class Delivery:
    def __init__(self):
        self.requests = []
    def deliver(self, request):
        self.requests.append(request)
        return ApprovalDeliveryReceipt("microsoft_teams", "provider-card-" + request.approval_id, NOW)


class NativeBoundary:
    def __init__(self, root, ports, delivery):
        self.delivery = delivery
        self.store = RootObjectiveStore(root=root, production=False)
        self.ports = ports
        self.effects = []
        self.receipts = {}
        self.timeout_after_effect = False
        self.readback_unavailable = False
        self.calls = []
        self.preflight_unavailable = False
        self.now = NOW
    def stage(self, *, proposal, requests, pending):
        material = {"requests": [request_material(r) for r in requests],
                    "scope": scope_material(proposal.scope)}
        staged = self.store.stage(approval_id=proposal.approval_id, material=material, at=NOW,
            policy_digest=self.ports["policy_digest"], allowed_components=frozenset({"documentation-publisher"}),
            allowed_requesters=frozenset({SERVICE}), native_preflight=lambda _: True)
        return staged
    def record_delivery(self, *, approval_id, receipt):
        self.store.record_delivery(approval_id=approval_id,
            provider_message_id=receipt.channel_reference_id,
            policy_digest=self.ports["policy_digest"],
            allowed_components=frozenset({"documentation-publisher"}))
    def call(self, operation, *, approval_id, step_index=None, signed_envelope=None):
        if operation == "status":
            return self.store.status(approval_id=approval_id)
        if operation == "admit":
            return self.store.admit(approval_id=approval_id, signed_envelope=signed_envelope,
                                    at=self.now, verify_ports=self.ports)
        if operation == "execute" and self.preflight_unavailable:
            from jason_runtime.owner_objective_root_client import ObjectiveRootRequestDenied
            raise ObjectiveRootRequestDenied("NATIVE_PREFLIGHT", "not_started")
        if operation == "readback" and not (self.store._plan(approval_id)/("claim-"+str(step_index)+".json")).exists():
            from jason_runtime.owner_objective_root_client import ObjectiveRootRequestDenied
            raise ObjectiveRootRequestDenied("NO_EXISTING_NATIVE_CLAIM", "not_started")
        if operation == "deliver":
            message_id = self.store.deliver(approval_id=approval_id, at=NOW,
                policy_digest=self.ports["policy_digest"],
                allowed_components=frozenset({"documentation-publisher"}),
                native_delivery=lambda _: self.delivery.deliver(SimpleNamespace(
                    approval_id=approval_id)).channel_reference_id)
            return {"approval_id": approval_id, "provider_message_id": message_id}
        self.calls.append((operation, step_index))
        claim = self.store.claim(approval_id=approval_id, step_index=step_index,
            signed_envelope=signed_envelope, at=self.now, verify_ports=self.ports,
            native_preflight=lambda *a: True, readback_only=operation == "readback")
        if operation == "execute" and not claim["already_verified"]:
            assert claim["claim_id"] not in self.effects
            self.effects.append(claim["claim_id"])
            args = claim["step_material"]["arguments"]
            self.receipts[claim["claim_id"]] = dict(status="verified", approval_id=approval_id,
                plan_fingerprint=claim["plan_fingerprint"], step_index=step_index,
                claim_id=claim["claim_id"], candidate_sha=args["candidate_sha"],
                scope_sha256=args["scope_sha256"], manifest_sha256=args["manifest_sha256"])
            if self.timeout_after_effect:
                raise TimeoutError("simulated connection loss after effect")
        if self.readback_unavailable:
            raise TimeoutError("simulated temporarily unavailable native readback")
        return self.store.complete_from_native_readback(approval_id=approval_id, step_index=step_index,
            native_readback=lambda c: self.receipts[c["claim_id"]])


@pytest.fixture
def env(tmp_path):
    authority_path, binding_path = tmp_path / "authority.db", tmp_path / "bindings.db"
    core = SQLiteIdentityAuthorityStore(authority_path)
    identities, grants = SQLiteIdentityRepository(core), SQLiteAuthorityGrantRepository(core)
    identities.put(IdentityRecord(OWNER, "human", "aot"))
    identities.put(IdentityRecord(SERVICE, "service", "aot"))
    names = (*CAPABILITIES, TEST_CAPABILITY)
    for principal in (OWNER, SERVICE):
        for index, name in enumerate(names):
            grants.put(AuthorityGrant(principal + str(index), principal, name, "aot", None,
                PermissionMode.EXECUTE, approval_required=principal == SERVICE))
    bindings = SQLiteMicrosoftIdentityBindingStore(binding_path)
    bindings.put(MicrosoftIdentityBinding(TENANT, LICENSED_OWNER, OWNER))
    args = dict(component_id="documentation-publisher", candidate_sha="a"*40,
        rollback_sha="d"*40, scope_sha256="1"*64, manifest_sha256="2"*64,
        freeze_sha256="3"*64, hold_sha256="4"*64)
    rules = [{"principal_id": SERVICE, "capability": name, "permission_mode": "execute",
              "client_id": None, "arguments_sha256": plan_digest(
                  {"test_only": True, "execution_permitted": False} if name == TEST_CAPABILITY else args)}
             for name in names]
    policy = {"schema_version": "1.0", "organizations": {"aot": {
        "role_members": {"owner": [OWNER]}, "capability_roles": {name: ["owner"] for name in names},
        "disabled_principals": [], "max_risk": 3, "production_allowed": True,
        "request_retention_allowed": True, "max_ttl_seconds": 86400,
        "service_requesters": {SERVICE: {"microsoft_tenant_id": TENANT, "maximum_plan_steps": 12}},
        "request_allowlist": rules}}}
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy))
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    der = key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    public_path, registry = tmp_path / "public.pem", tmp_path / "keys.json"
    public_path.write_bytes(public)
    registry.write_text(json.dumps({"keys": [{"key_id": "test-gateway", "machine_identity": "gateway",
        "public_key_path": str(public_path), "sha256_fingerprint": sha256(der).hexdigest()}]}))
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    config = dict(schema_version="1.0", enabled=True, state_dir=str(state),
        authority_db=str(authority_path), bindings_db=str(binding_path), trusted_keys_registry=str(registry),
        allowed_machine_identities=["gateway"], plans_db=str(state / "plans.sqlite3"),
        policy_path=str(policy_path), spool=str(tmp_path / "unused"), requester_identity_id=SERVICE,
        objective_ttl_seconds=86400, campaign=dict(deny_approval_id="planapproval-objective-"+"0"*32,
            approve_approval_id="planapproval-objective-"+"1"*32, issued_at=NOW.isoformat(), step_arguments=args))
    delivery = Delivery()
    with tempfile.TemporaryDirectory(prefix="objective-component-", dir="/tmp") as temporary:
        root = Path(temporary); root.chmod(0o700)
        from jason_openclaw.signed_transport import Ed25519TransportAuthenticator
        ports = dict(authenticator=Ed25519TransportAuthenticator({"test-gateway": public}, {"test-gateway": "gateway"}),
            allowed_machine_identities=frozenset({"gateway"}), policy_digest=plan_digest(policy),
            allowed_components=frozenset({"documentation-publisher"}),
            current_owner_identity=lambda tenant, oid: OWNER if (tenant,oid)==(TENANT,LICENSED_OWNER) else None)
        native = NativeBoundary(root, ports, delivery)
        app = build(config, delivery=delivery, root_client=native, clock=lambda:NOW)
        yield SimpleNamespace(app=app, config=config, native=native, delivery=delivery, key=key,
                              grants=grants, identities=identities)


def signed(env, case, decision):
    approval_id = env.config["campaign"].get(case + "_approval_id", case)
    pending = env.app.handler.service.teams_flow.approval_service.repository.get(approval_id)
    envelope = dict(kind="conversation.turn", request_id="transport-"+approval_id,
        correlation_id=approval_id, issued_at=NOW.isoformat(), expires_at=(NOW+timedelta(seconds=90)).isoformat(),
        nonce="nonce-"+approval_id, channel="msteams", text="Reviewed Owner decision",
        transport_identity=dict(microsoft_tenant_id=TENANT, microsoft_object_id=LICENSED_OWNER,
                                authentication_assurance="botframework-authenticated"),
        conversation_id="test-conversation", message_id="callback-"+approval_id, key_id="test-gateway",
        interaction=dict(kind="approval.submit", approval_id=approval_id, decision=decision,
            channel_response_id="callback-"+approval_id,
            callback_reply_to_id="provider-card-"+approval_id,
            selections={"card_challenge": pending.metadata["card_instance_challenge"]}))
    envelope["signature"] = base64.b64encode(env.key.sign(canonical_signed_payload(envelope))).decode()
    return envelope


def deny_then_issue(env):
    env.app.maintenance()
    assert len(env.delivery.requests) == 1 and not env.native.effects
    assert env.app.interaction(signed(env, "deny", "deny"))["executed"] is False
    assert env.app.handler.service.teams_flow.approval_service.repository.accepted_decision(
        env.config["campaign"]["deny_approval_id"]).status == "denied"
    env.app.maintenance()
    assert len(env.delivery.requests) == 2 and not env.native.effects


def test_one_original_teams_approve_completes_both_registered_root_steps(env):
    deny_then_issue(env)
    assert env.app.interaction(signed(env, "approve", "approve"))["executed"] is False
    env.app.maintenance()
    approval = env.config["campaign"]["approve_approval_id"]
    assert env.app.handler.requests.progress(approval)["state"] == "completed"
    assert env.native.store.status(approval_id=approval)["state"] == "verified_complete"
    assert len(set(env.native.effects)) == 2
    restarted = build(env.config, delivery=env.delivery, root_client=env.native, clock=lambda:NOW)
    restarted.maintenance()
    assert len(env.delivery.requests) == 2 and len(env.native.effects) == 2


def test_mistaken_approve_on_deny_test_cannot_execute_or_issue_production_card(env):
    env.app.maintenance()
    env.app.interaction(signed(env, "deny", "approve"))
    env.app.maintenance()
    assert len(env.delivery.requests) == 1 and not env.native.effects


def test_lost_result_recovers_by_readback_without_second_vote_or_effect(env):
    deny_then_issue(env)
    env.app.interaction(signed(env, "approve", "approve"))
    env.native.timeout_after_effect = env.native.readback_unavailable = True
    env.app.maintenance()
    approval = env.config["campaign"]["approve_approval_id"]
    assert env.app.handler.requests.progress(approval)["state"] == "indeterminate"
    assert len(env.native.effects) == 1
    child = "planstep-" + sha256((approval+"|"+approval+"-0|"+
        env.app.handler.proposals.require(approval).plan_fingerprint).encode()).hexdigest()
    assert env.app.execution.evidence(child)["state"] == "consumed"
    env.native.timeout_after_effect = env.native.readback_unavailable = False
    restarted = build(env.config, delivery=env.delivery, root_client=env.native, clock=lambda:NOW)
    restarted.maintenance()
    progress = restarted.handler.requests.progress(approval)
    assert progress["state"] == "completed", progress
    assert len(env.native.effects) == 2 and len(env.delivery.requests) == 2
    assert env.native.calls.count(("execute", 0)) == 1
    assert restarted.execution.evidence(child)["state"] == "succeeded"


def test_restart_before_root_send_recovers_first_send_without_second_card(env,monkeypatch):
    env.app.maintenance()
    env.app.interaction(signed(env,"deny","deny"))
    original=env.native.call
    def crash(operation,**kwargs):
        if operation=="deliver":raise SystemExit("synthetic stop before Root send")
        return original(operation,**kwargs)
    monkeypatch.setattr(env.native,"call",crash)
    with pytest.raises(SystemExit):env.app.maintenance()
    assert len(env.delivery.requests)==1
    monkeypatch.setattr(env.native,"call",original)
    restarted=build(env.config,delivery=env.delivery,root_client=env.native,clock=lambda:NOW)
    restarted.maintenance();restarted.maintenance()
    assert len(env.delivery.requests)==2
    env.app=restarted
    restarted.interaction(signed(env,"approve","approve"))
    restarted.maintenance()
    approval=env.config["campaign"]["approve_approval_id"]
    assert restarted.handler.requests.progress(approval)["state"]=="completed"
    assert len(env.native.effects)==2


def test_current_service_grant_revocation_blocks_remaining_step_without_second_vote(env,monkeypatch):
    deny_then_issue(env)
    env.app.interaction(signed(env,"approve","approve"))
    original=env.native.call
    def revoke_after_first(operation,**kwargs):
        result=original(operation,**kwargs)
        if operation=="execute" and kwargs["step_index"]==0:
            env.grants.revoke(SERVICE+"1")
        return result
    monkeypatch.setattr(env.native,"call",revoke_after_first)
    env.app.maintenance()
    approval=env.config["campaign"]["approve_approval_id"]
    assert env.app.handler.requests.progress(approval)["state"]=="blocked"
    assert len(env.native.effects)==1 and len(env.delivery.requests)==2


def test_transient_native_gate_keeps_original_decision_and_first_effect_after_transport_expiry(env):
    deny_then_issue(env)
    env.app.interaction(signed(env,"approve","approve"))
    env.native.preflight_unavailable=True
    env.app.maintenance()
    approval=env.config["campaign"]["approve_approval_id"]
    assert env.app.handler.requests.progress(approval)["state"]=="indeterminate"
    assert not env.native.effects
    env.native.preflight_unavailable=False
    later=NOW+timedelta(minutes=10)
    env.native.now=later
    restarted=build(env.config,delivery=env.delivery,root_client=env.native,clock=lambda:later)
    restarted.maintenance()
    progress=restarted.handler.requests.progress(approval)
    assert progress["state"]=="completed",progress
    assert len(env.native.effects)==2 and len(env.delivery.requests)==2
    decision=env.native.store._read(env.native.store._plan(approval)/"verified-decision.json")
    assert decision["verified_at"]==NOW.isoformat()

def complete_acceptance(env):
    deny_then_issue(env)
    env.app.interaction(signed(env, "approve", "approve"))
    env.app.maintenance()


def test_later_registered_objective_uses_one_new_decision_without_root_reinstallation(env):
    complete_acceptance(env)
    request_id = "2" * 32
    result = env.app.submit_registered(template_id="documentation-publisher", request_id=request_id)
    approval = result["approval_id"]
    assert approval == "planapproval-objective-" + request_id
    assert len(env.delivery.requests) == 3 and len(env.native.effects) == 2
    # A retried request and a component restart retain the same manifest/card.
    again = env.app.submit_registered(template_id="documentation-publisher", request_id=request_id)
    assert again == result
    restarted = build(env.config, delivery=env.delivery, root_client=env.native, clock=lambda:NOW)
    env.app = restarted
    assert restarted.submit_registered(template_id="documentation-publisher", request_id=request_id) == result
    assert len(env.delivery.requests) == 3 and len(env.native.effects) == 2
    restarted.interaction(signed(env, approval, "approve"))
    restarted.maintenance()
    assert restarted.submission_status(request_id=request_id)["state"] == "completed"
    assert env.native.store.status(approval_id=approval)["state"] == "verified_complete"
    assert len(env.native.effects) == 4 and len(env.delivery.requests) == 3


def test_submissions_require_real_initial_acceptance_and_bounded_active_work(env):
    with pytest.raises(PermissionError, match="LIVE_OWNER_ACCEPTANCE_REQUIRED"):
        env.app.submit_registered(template_id="documentation-publisher", request_id="2"*32)
    complete_acceptance(env)
    for number in ("2", "3"):
        env.app.submit_registered(template_id="documentation-publisher", request_id=number*32)
    with pytest.raises(PermissionError, match="ACTIVE_LIMIT"):
        env.app.submit_registered(template_id="documentation-publisher", request_id="4"*32)
    assert len(env.delivery.requests) == 4 and len(env.native.effects) == 2


@pytest.mark.parametrize("template,identifier", [
    ("shell", "2"*32), ("documentation-publisher", "../escape"),
    ("documentation-publisher", "1"*32), ("documentation-publisher", 123)])
def test_submission_cannot_change_template_or_reuse_reserved_id(env,template,identifier):
    with pytest.raises(PermissionError):
        env.app.submit_registered(template_id=template,request_id=identifier)
    assert not env.native.effects and not env.delivery.requests


def test_interrupted_submission_retains_initial_manifest_time_and_does_not_resend(env,monkeypatch):
    complete_acceptance(env)
    original=env.native.call
    def crash(operation,**kwargs):
        if operation=="deliver":raise SystemExit("stop before first later-objective delivery")
        return original(operation,**kwargs)
    monkeypatch.setattr(env.native,"call",crash)
    with pytest.raises(SystemExit):
        env.app.submit_registered(template_id="documentation-publisher",request_id="2"*32)
    monkeypatch.setattr(env.native,"call",original)
    later=NOW+timedelta(minutes=10)
    env.native.now=later
    env.app=build(env.config,delivery=env.delivery,root_client=env.native,clock=lambda:later)
    result=env.app.submit_registered(template_id="documentation-publisher",request_id="2"*32)
    assert result["expires_at"]==(NOW+timedelta(days=1)).isoformat()
    assert len(env.delivery.requests)==3

def test_restart_after_root_stage_before_canonical_storage_uses_same_submission_manifest(env,monkeypatch):
    complete_acceptance(env)
    original=env.native.stage
    def crash(**kwargs):
        original(**kwargs)
        raise SystemExit("stop after Root stage before canonical storage")
    monkeypatch.setattr(env.native,"stage",crash)
    with pytest.raises(SystemExit):
        env.app.submit_registered(template_id="documentation-publisher",request_id="2"*32)
    assert len(env.delivery.requests)==2
    monkeypatch.setattr(env.native,"stage",original)
    later=NOW+timedelta(minutes=10);env.native.now=later
    env.app=build(env.config,delivery=env.delivery,root_client=env.native,clock=lambda:later)
    env.app.maintenance()
    result=env.app.submission_status(request_id="2"*32)
    assert result["expires_at"]==(NOW+timedelta(days=1)).isoformat()
    assert len(env.delivery.requests)==3 and len(env.native.effects)==2
