"""Real signatures and the canonical retained plan; no live Teams/root changes."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from jason_openclaw.signed_transport import Ed25519TransportAuthenticator, canonical_signed_payload
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.teams_plan_request_repository import plan_fingerprint, request_material, scope_material
from tools import pmv4_teams_objective_admission as a

NOW = datetime(2026, 11, 21, 4, 0, tzinfo=timezone.utc)


@pytest.fixture
def case():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    auth = Ed25519TransportAuthenticator({"gateway": public}, {"gateway": "registered-gateway"})
    approval_id = "planapproval-" + "a" * 32
    scope = ApprovedPlanScope("plan-" + approval_id, "aot", "b" * 64,
        frozenset({"release.documentation.publisher.restore", "release.documentation.publisher.verify"}),
        frozenset(), 3, True, NOW + timedelta(hours=1))
    args = dict(component_id="documentation-publisher", candidate_sha="c" * 40,
        rollback_sha="d" * 40, scope_sha256="e" * 64, manifest_sha256="f" * 64,
        freeze_sha256="1" * 64, hold_sha256="2" * 64)
    steps = tuple(OrchestrationRequest(
        "release-step-" + str(i), "objective-test", "jason-release-manager", "aot",
        capability, "1.0.0", "deterministic", OrchestrationMode.EXECUTE,
        False, False, "critical", DataHandlingPolicy("internal", False, retention_allowed=True),
        ExecutionBudget(Decimal("0")), arguments=args, client_id=None,
        permission_mode="execute", requester_kind="service")
        for i, capability in enumerate(sorted(scope.allowed_capabilities)))
    material = {"requests": [request_material(s) for s in steps], "scope": scope_material(scope)}
    enrolled = dict(schema_version="1.0", approval_id=approval_id,
        plan_fingerprint=plan_fingerprint(steps, scope), material=material,
        card_instance_challenge="3" * 48, provider_message_id="actual-provider-message-1",
        staged_at=(NOW - timedelta(minutes=1)).isoformat())
    envelope = {
        "kind": "conversation.turn", "channel": "msteams", "key_id": "gateway",
        "issued_at": NOW.isoformat(), "expires_at": (NOW + timedelta(seconds=90)).isoformat(),
        "transport_identity": {"microsoft_tenant_id": a.TENANT,
            "microsoft_object_id": a.LICENSED_OWNER, "authentication_assurance": "botframework-authenticated"},
        "message_id": "actual-click-1", "conversation_id": "owner-conversation",
        "interaction": {"kind": "approval.submit", "approval_id": approval_id,
            "decision": "approve", "channel_response_id": "actual-click-1",
            "selections": {"card_challenge": enrolled["card_instance_challenge"]},
            "callback_reply_to_id": enrolled["provider_message_id"]},
    }
    def sign():
        envelope["signature"] = base64.b64encode(private.sign(canonical_signed_payload(envelope))).decode()
    sign()
    def verify(**overrides):
        params = dict(enrollment=enrolled, signed_envelope=envelope, authenticator=auth,
            allowed_machine_identities=frozenset({"registered-gateway"}),
            policy_digest="b" * 64, allowed_components=frozenset({"documentation-publisher"}),
            current_owner_identity=lambda tenant, oid: "person-entra-" + oid.replace("-", ""), at=NOW)
        return a.verify_original_teams_decision(**(params | overrides))
    verify.ports = dict(authenticator=auth,
        allowed_machine_identities=frozenset({"registered-gateway"}),
        policy_digest="b" * 64, allowed_components=frozenset({"documentation-publisher"}),
        current_owner_identity=lambda tenant, oid: "person-entra-" + oid.replace("-", ""))
    return enrolled, envelope, sign, verify


def test_one_real_signed_decision_covers_distinct_ordered_claims(case):
    enrolled, envelope, sign, verify = case
    decision = verify()
    steps = enrolled["material"]["requests"]
    assert len({decision.claim_id(i, step) for i, step in enumerate(steps)}) == 2
    assert decision.approval_id == enrolled["approval_id"]
    assert decision.evidence_sha256 == sha256(canonical_signed_payload(envelope)).hexdigest()


def test_retained_root_verification_survives_transport_expiry_within_plan_lifetime(case):
    _, _, _, verify = case
    later = NOW + timedelta(minutes=15)
    with pytest.raises(a.TeamsObjectiveDenied, match="DECISION_FRESHNESS"):
        verify(at=later)
    assert verify(at=later, previously_verified_at=NOW).decided_at == NOW
    with pytest.raises(a.TeamsObjectiveDenied, match="PLAN_EXPIRED"):
        verify(at=NOW + timedelta(hours=2), previously_verified_at=NOW)


@pytest.mark.parametrize("fault", [
    "wrong_tenant", "wrong_owner", "bot_actor", "deny", "different_approval", "different_receipt",
    "challenge", "missing_reply_to", "wrong_original_message", "synthetic_provider_message",
    "forged_signature", "policy_changed", "inactive_owner", "new_step", "new_artifact",
    "new_component", "caller_execution_authority", "wrong_source", "expired_plan",
])
def test_changed_human_plan_or_origin_never_passes_root_admission(case, fault):
    enrolled, envelope, sign, verify = case
    options = {}
    if fault == "wrong_tenant": envelope["transport_identity"]["microsoft_tenant_id"] = "foreign"
    if fault == "wrong_owner": envelope["transport_identity"]["microsoft_object_id"] = "foreign"
    if fault == "bot_actor": envelope["transport_identity"]["authentication_assurance"] = "workload_identity"
    if fault == "deny": envelope["interaction"]["decision"] = "deny"
    if fault == "different_approval": envelope["interaction"]["approval_id"] = "planapproval-" + "9" * 32
    if fault == "different_receipt": envelope["interaction"]["channel_response_id"] = "different"
    if fault == "challenge": envelope["interaction"]["selections"]["card_challenge"] = "4" * 48
    if fault == "missing_reply_to": envelope["interaction"].pop("callback_reply_to_id")
    if fault == "wrong_original_message": envelope["interaction"]["callback_reply_to_id"] = "different"
    if fault == "synthetic_provider_message": enrolled["provider_message_id"] = "accepted:synthetic"
    if fault == "policy_changed": options["policy_digest"] = "9" * 64
    if fault == "inactive_owner": options["current_owner_identity"] = lambda *a: None
    if fault == "new_step": enrolled["material"]["requests"].append(deepcopy(enrolled["material"]["requests"][0]))
    if fault == "new_artifact": enrolled["material"]["requests"][0]["arguments"]["manifest_sha256"] = "9" * 64
    if fault == "new_component": options["allowed_components"] = frozenset({"different"})
    if fault == "caller_execution_authority": enrolled["material"]["requests"][0]["authority_allowed"] = True
    if fault == "wrong_source": enrolled["material"]["requests"][0]["arguments"]["candidate_sha"] = "branch-name"
    if fault == "expired_plan": options["at"] = NOW + timedelta(hours=2)
    sign()
    if fault == "forged_signature": envelope["signature"] = base64.b64encode(b"0" * 64).decode()
    with pytest.raises(a.TeamsObjectiveDenied):
        verify(**options)
