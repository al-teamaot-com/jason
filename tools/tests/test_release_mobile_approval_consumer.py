"""Signed and durable owner consent becomes exact CCC review + release approval."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestService, SQLiteApprovalRequestRepository,
)
from jason_openclaw.signed_transport import Ed25519TransportAuthenticator, canonical_signed_payload
from jason_runtime.mobile_release_approval import (
    MobileReleaseApprovalFlow, MobileReleaseOwnerAuthority, MobileReleaseSignedEvidenceStore,
    read_mobile_release_policy, read_eligible_release, create_mobile_release_request,
)
from jason_runtime.universal_teams_approval import SignedTeamsApprovalEvidenceVerifier
from kernel.identity_authority import IdentityRecord, SQLiteIdentityAuthorityStore, SQLiteIdentityRepository
from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore
from release_mobile_approval_consumer import consume_mobile_release_decisions

SHA = "9adde7fd62c0ca6ce0e1c1578b75cb8751841dfa"
ROLLBACK = "71edbeabfdec2fa5dcb43022ac8fdc44a4c77334"
NOW = datetime.now(timezone.utc).replace(microsecond=0)  # avoid expired historical fixture
RID = "release-" + SHA[:16]


def fixture(tmp_path, *, approve=True):
    from implementation.runtime_service.tests.test_mobile_release_approval import policy_file, release_record
    policy_path = policy_file(tmp_path)
    root, release_path = release_record(tmp_path)
    ccc = tmp_path / "ccc"
    ccc.mkdir()
    policy = read_mobile_release_policy(policy_path)
    request = create_mobile_release_request(read_eligible_release(root, RID, policy), policy, now=NOW)
    path = tmp_path / "approvals.sqlite3"
    repo = SQLiteApprovalRequestRepository(path)
    svc = ApprovalRequestService(repo, MobileReleaseOwnerAuthority(policy_path))
    svc.create(request, now=NOW)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    public_path = tmp_path / "gateway.pem"
    public_path.write_bytes(public)
    der = private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    registry = tmp_path / "key-registry.json"
    registry.write_text(json.dumps({"keys": [{
        "key_id": "gateway-key", "machine_identity": "svc-openclaw-gateway",
        "public_key_path": str(public_path),
        "sha256_fingerprint": hashlib.sha256(der).hexdigest(), "status": "active",
    }]}), encoding="utf-8")
    authenticator = Ed25519TransportAuthenticator(
        {"gateway-key": public}, {"gateway-key": "svc-openclaw-gateway"},
    )
    verifier = SignedTeamsApprovalEvidenceVerifier(
        authenticator=authenticator,
        allowed_machine_identities=frozenset({"svc-openclaw-gateway"}),
        allowed_approval_prefixes=("relapproval-",),
        clock=lambda: NOW,
    )
    bindings_db = tmp_path / "bindings.sqlite3"
    bindings = SQLiteMicrosoftIdentityBindingStore(bindings_db)
    bindings.put(MicrosoftIdentityBinding("tenant-a", "object-al", "person-al"))
    authority_db = tmp_path / "authority.sqlite3"
    identities = SQLiteIdentityRepository(SQLiteIdentityAuthorityStore(authority_db))
    identities.put(IdentityRecord("person-al", "human", "aot"))
    store = MobileReleaseSignedEvidenceStore(path)
    flow = MobileReleaseApprovalFlow(svc, repo, policy_path, root, bindings,
                                     identities, verifier, store)
    decision = "approve" if approve else "deny"
    envelope = {
        "kind": "conversation.turn",
        "request_id": "signed-retest-" + request.approval_id,
        "correlation_id": "mobile-release-signed-test",
        "issued_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
        "nonce": "unique-" + request.approval_id,
        "channel": "msteams",
        "text": "Mobile production release review",
        "transport_identity": {
            "microsoft_tenant_id": "tenant-a", "microsoft_object_id": "object-al",
            "authentication_assurance": "botframework-authenticated",
        },
        "conversation_id": "teams-owner-chat",
        "message_id": "teams-response-1",
        "interaction": {
            "kind": "approval.submit", "approval_id": request.approval_id,
            "decision": decision, "channel_response_id": "teams-response-1", "selections": {},
        },
        "key_id": "gateway-key",
    }
    envelope["signature"] = base64.b64encode(private.sign(canonical_signed_payload(envelope))).decode()
    args = {
        "approval_id": request.approval_id, "decision": decision,
        "microsoft_tenant_id": "tenant-a", "microsoft_object_id": "object-al",
        "conversation_id": "teams-owner-chat", "channel_response_id": "teams-response-1",
        "decided_at": NOW, "signed_envelope": envelope, "selections": {},
    }
    opts = dict(
        repo=tmp_path, state_root=root, database=path, policy_file=policy_path, ccc_root=ccc,
        bindings_db=bindings_db, authority_db=authority_db, trusted_keys=registry,
    )
    return flow, repo, release_path, request, args, opts, identities, bindings


def test_signed_owner_decision_issues_exact_ccc_and_release_then_idempotent(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    accepted = flow.handle(**args)
    assert accepted["approval_status"] == "approved"
    assert accepted["executed"] is False
    calls = []

    def approve(_repo, _root, *, release_id, candidate_sha, source):
        assert release_id == RID and candidate_sha == SHA
        assert source == "authenticated_mobile_teams_owner:" + request.approval_id
        calls.append(source)

    opts["approve_release"] = approve
    assert consume_mobile_release_decisions(**opts) == 1
    review = json.loads((opts["ccc_root"] / "material-review.json").read_text())
    assert review["source_revision"] == SHA
    assert review["recorded_by"] == "person-al"
    assert review["mobile_approval_id"] == request.approval_id
    assert review["status"] == "approved"
    assert review["signed_evidence_sha256"] == repo.accepted_decision(request.approval_id).authentication_evidence_hash
    assert (opts["ccc_root"] / ("material-review-" + SHA[:16] + ".json")).exists()
    assert len(calls) == 1
    assert consume_mobile_release_decisions(**opts) == 0
    assert len(calls) == 1


def test_deny_never_produces_release_or_ccc_authority(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path, approve=False)
    result = flow.handle(**args)
    assert result["approval_status"] == "denied"
    opts["approve_release"] = lambda *_args, **_kwargs: pytest.fail("deny cannot approve")
    assert consume_mobile_release_decisions(**opts) == 0
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_changed_release_blocks_consumption_even_after_authentic_click(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    original = json.loads(release_path.read_text())
    original["release_manifest"]["changed_files"].append("another-program.py")
    release_path.write_text(json.dumps(original))
    opts["approve_release"] = lambda *_args, **_kwargs: pytest.fail("stale reviewed release cannot be approved")
    with pytest.raises(PermissionError, match="changed"):
        consume_mobile_release_decisions(**opts)
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_revoked_owner_or_modified_signed_envelope_blocks_host_proof(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    import sqlite3
    conn=sqlite3.connect(opts["database"])
    record=conn.execute("SELECT signed_envelope_json FROM mobile_release_signed_evidence WHERE approval_id=?",(request.approval_id,)).fetchone()
    bad=json.loads(record[0]);bad["interaction"]["decision"]="deny"
    conn.execute("UPDATE mobile_release_signed_evidence SET signed_envelope_json=? WHERE approval_id=?",(json.dumps(bad),request.approval_id))
    conn.commit();conn.close()
    opts["approve_release"] = lambda *_args, **_kwargs: pytest.fail("tamper cannot approve")
    with pytest.raises(PermissionError):
        consume_mobile_release_decisions(**opts)
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_no_mobile_ledger_means_no_action_and_manual_flow_untouched(tmp_path):
    calls=[]
    assert consume_mobile_release_decisions(
        repo=tmp_path,state_root=tmp_path,approve_release=lambda *a,**k:calls.append(1),
        database=tmp_path/"absent.sqlite3", policy_file=tmp_path/"absent-policy.json",
    ) == 0
    assert calls == []


def test_crash_after_exact_owner_record_restores_only_verified_marker(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)

    def approve(_repo, _root, *, release_id, candidate_sha, source):
        j = json.loads(release_path.read_text())
        j["owner_approval"] = {
            "approved": True, "candidate_sha": candidate_sha, "source": source,
        }
        j["state"] = "production"
        release_path.write_text(json.dumps(j))

    opts["approve_release"] = approve
    assert consume_mobile_release_decisions(**opts) == 1
    marker = opts["state_root"] / "mobile-release-decisions-processed" / (request.approval_id + ".json")
    marker.unlink()
    assert consume_mobile_release_decisions(**opts) == 0
    assert json.loads(marker.read_text())["recovery"] == "previous_exact_owner_approval_verified"


def test_actual_delivered_card_signed_click_and_independent_host_attestation(tmp_path):
    """Prove real worker's delivery ledger mutation cannot cause a Teams 403.

    Both runtime signed ingress and host release/CCC revalidation must accept
    the *same* bounded delivery receipt without changing immutable authority.
    """
    from dataclasses import replace
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    repo.put(replace(
        request, metadata={
            **request.metadata, "delivery_message_ids": "accepted:test-transport-receipt",
        },
    ))
    result = flow.handle(**args)
    assert result["approval_status"] == "approved"
    assert result["executed"] is False
    applied = []
    opts["approve_release"] = lambda _repo, _root, *, release_id, candidate_sha, source: (
        applied.append((release_id, candidate_sha, source))
    )
    assert consume_mobile_release_decisions(**opts) == 1
    assert len(applied) == 1
    assert applied[0] == (
        RID, SHA, "authenticated_mobile_teams_owner:" + request.approval_id,
    )
    review = json.loads((opts["ccc_root"] / "material-review.json").read_text())
    assert review["source_revision"] == SHA
    assert review["recorded_by"] == "person-al"
    assert review["mobile_approval_id"] == request.approval_id
    assert consume_mobile_release_decisions(**opts) == 0


def test_transport_delivery_receipt_does_not_weaken_policy_or_manifest_gate(tmp_path):
    from dataclasses import replace
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    repo.put(replace(
        request, metadata={
            **request.metadata, "delivery_message_ids": "accepted:test-transport-receipt",
        },
    ))
    data = json.loads(release_path.read_text())
    data["release_manifest"]["changed_files"].append("unreviewed.py")
    release_path.write_text(json.dumps(data))
    with pytest.raises(PermissionError):
        flow.handle(**args)
    assert repo.accepted_decision(request.approval_id) is None
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_p0_owner_hold_blocks_already_recorded_signed_approval_before_host_ccc(tmp_path):
    """A previously accepted Teams callback must not authorize CCC when held."""
    from datetime import timedelta
    from jason_runtime.owner_release_approval_containment import HOLD_FILENAME
    flow, repo, record, request, args, opts, identities, bindings = fixture(tmp_path)
    signed = flow.handle(**args)
    assert signed["approval_status"] == "approved"
    holds = opts["state_root"] / HOLD_FILENAME
    holds.write_text(json.dumps({
        "schema_version":"1.0",
        "capability":"release.production.approve",
        "state":"held",
        "hold_id":"P0-1553",
        "hold_started_at":(NOW+timedelta(seconds=1)).isoformat(),
    }))
    holds.chmod(0o600)
    calls=[]
    opts["approve_release"] = lambda *_args,**_kwargs:calls.append(1)
    assert consume_mobile_release_decisions(**opts)==0
    assert calls==[]
    assert not (opts["ccc_root"]/"material-review.json").exists()
    assert not (opts["state_root"]/"mobile-release-decisions-processed"/
                (request.approval_id+".json")).exists()


def test_releasing_hold_cannot_revive_old_signed_decision(tmp_path):
    from datetime import timedelta
    from jason_runtime.owner_release_approval_containment import HOLD_FILENAME
    flow, repo, record, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    hold = opts["state_root"]/HOLD_FILENAME
    payload={
        "schema_version":"1.0",
        "capability":"release.production.approve",
        "state":"released",
        "hold_id":"P0-1553",
        "hold_started_at":(NOW+timedelta(seconds=1)).isoformat(),
        "released_at":(NOW+timedelta(minutes=5)).isoformat(),
    }
    hold.write_text(json.dumps(payload));hold.chmod(0o600)
    calls=[]
    opts["approve_release"]=lambda *_args,**_kwargs:calls.append(1)
    assert consume_mobile_release_decisions(**opts)==0
    assert calls==[]
    assert repo.accepted_decision(request.approval_id) is not None
    assert not (opts["ccc_root"]/"material-review.json").exists()


def test_malformed_containment_prevents_host_material_review(tmp_path):
    from jason_runtime.owner_release_approval_containment import HOLD_FILENAME
    flow, repo, record, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    hold = opts["state_root"]/HOLD_FILENAME
    hold.write_text('{"state":"off"}');hold.chmod(0o600)
    opts["approve_release"] = lambda *_args,**_kwargs: pytest.fail(
        "malformed hold cannot mint CCC material review"
    )
    with pytest.raises(PermissionError,match="policy_invalid"):
        consume_mobile_release_decisions(**opts)
    assert not (opts["ccc_root"]/"material-review.json").exists()
