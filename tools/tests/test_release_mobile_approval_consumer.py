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


def fixture(tmp_path, *, approve=True, reviewed=False, card_selection_override=None,
            review_only=False):
    from implementation.runtime_service.tests.test_mobile_release_approval import (
        policy_file, reviewed_policy_file, mark_release_high_impact, release_record,
    )
    policy_path = reviewed_policy_file(tmp_path) if reviewed else policy_file(tmp_path)
    root, release_path = release_record(tmp_path)
    if reviewed:
        mark_release_high_impact(root)
    if review_only:
        assert reviewed
        record = json.loads(release_path.read_text(encoding="utf-8"))
        record["owner_approval"] = {
            "approved": True,
            "candidate_sha": SHA,
            "source": "explicit_owner_instruction",
            "recorded_at": NOW.isoformat(),
        }
        release_path.write_text(json.dumps(record), encoding="utf-8")
    ccc = tmp_path / "ccc"
    ccc.mkdir()
    policy = read_mobile_release_policy(policy_path)
    request = create_mobile_release_request(
        read_eligible_release(
            root, RID, policy, allow_existing_owner_approval=review_only,
        ),
        policy, now=NOW,
    )
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
        allowed_selection_keys=(frozenset({"card_challenge"}) if reviewed else frozenset()),
        clock=lambda: NOW,
    )
    bindings_db = tmp_path / "bindings.sqlite3"
    bindings = SQLiteMicrosoftIdentityBindingStore(bindings_db)
    bindings.put(MicrosoftIdentityBinding("tenant-a", "object-al", "person-al"))
    authority_db = tmp_path / "authority.sqlite3"
    identities = SQLiteIdentityRepository(SQLiteIdentityAuthorityStore(authority_db))
    identities.put(IdentityRecord("person-al", "human", "aot"))
    store = MobileReleaseSignedEvidenceStore(path)
    flow = MobileReleaseApprovalFlow(
        svc, repo, policy_path, root, bindings, identities, verifier, store,
        required_policy_version="2.0" if reviewed else "1.0",
    )
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
            "decision": decision, "channel_response_id": "teams-response-1",
            "selections": (
                {"card_challenge": request.metadata["card_instance_challenge"]}
                if reviewed else {}
            ),
        },
        "key_id": "gateway-key",
    }
    if card_selection_override is not None:
        envelope["interaction"]["selections"] = card_selection_override
    envelope["signature"] = base64.b64encode(private.sign(canonical_signed_payload(envelope))).decode()
    args = {
        "approval_id": request.approval_id, "decision": decision,
        "microsoft_tenant_id": "tenant-a", "microsoft_object_id": "object-al",
        "conversation_id": "teams-owner-chat", "channel_response_id": "teams-response-1",
        "decided_at": NOW, "signed_envelope": envelope,
        "selections": envelope["interaction"]["selections"],
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


def test_signed_protected_core_owner_approval_produces_one_exact_ccc_release_grant(tmp_path):
    """Actual Ed25519 signed callback and independent host consumer, no provider write."""
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True,
    )
    assert json.loads(release_path.read_text())["risk_profile"] == "production_control_core"
    before = release_path.read_bytes()
    callback = flow.handle(**args)
    assert callback["approval_status"] == "approved" and callback["executed"] is False
    assert release_path.read_bytes() == before
    # A genuine signed callback never directly marks CCC PASS or deploys.
    assert not (opts["ccc_root"] / "material-review.json").exists()
    calls = []
    opts["approve_release"] = lambda _repo, _state, *, release_id, candidate_sha, source: (
        calls.append((release_id, candidate_sha, source))
    )
    assert consume_mobile_release_decisions(**opts) == 1
    assert calls == [(RID, SHA, "authenticated_mobile_teams_owner:" + request.approval_id)]
    review = json.loads((opts["ccc_root"] / "material-review.json").read_text())
    assert review["source_revision"] == SHA
    assert review["recorded_by"] == "person-al"
    assert review["status"] == "approved"  # material review, NOT CCC certification PASS
    assert review["mobile_approval_id"] == request.approval_id
    assert review["signed_evidence_sha256"] == repo.accepted_decision(
        request.approval_id
    ).authentication_evidence_hash
    assert consume_mobile_release_decisions(**opts) == 0
    assert len(calls) == 1


def test_signed_protected_core_click_without_issued_card_nonce_fails_closed(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, card_selection_override={},
    )
    # This envelope is genuinely signed and owner-bound, but would result from
    # crafted activity.value instead of the originally issued V2 card.
    with pytest.raises(PermissionError, match="card instance"):
        flow.handle(**args)
    assert repo.accepted_decision(request.approval_id) is None
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_signed_protected_core_wrong_card_nonce_fails_closed(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, card_selection_override={"card_challenge": "0" * 48},
    )
    with pytest.raises(PermissionError, match="card instance"):
        flow.handle(**args)
    assert repo.accepted_decision(request.approval_id) is None


def test_signed_protected_core_deny_never_marks_material_ccc_or_owner_grant(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, approve=False,
    )
    assert flow.handle(**args)["approval_status"] == "denied"
    opts["approve_release"] = lambda *_args, **_kwargs: pytest.fail(
        "denied protected release cannot enter production approval"
    )
    assert consume_mobile_release_decisions(**opts) == 0
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_signed_protected_core_policy_drift_denies_host_consumer(tmp_path):
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True,
    )
    flow.handle(**args)
    # A separately changed reviewed risk set invalidates prior Teams consent.
    document = json.loads(opts["policy_file"].read_text())
    document["allowed_risk_profiles"] = ["normal"]
    opts["policy_file"].write_text(json.dumps(document))
    opts["approve_release"] = lambda *_args, **_kwargs: pytest.fail(
        "stale policy cannot authorize high impact production"
    )
    with pytest.raises(PermissionError):
        consume_mobile_release_decisions(**opts)
    assert not (opts["ccc_root"] / "material-review.json").exists()


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


def test_completed_mobile_decisions_require_no_authority_db_access_even_if_locked(tmp_path):
    """Six finished live decisions must not reinitialize the shared authority DB."""
    import sqlite3
    from unittest.mock import patch
    from kernel.identity_authority import SQLiteIdentityAuthorityStore
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    approvals = []
    opts["approve_release"] = lambda *a, **kw: approvals.append(kw)
    assert consume_mobile_release_decisions(**opts) == 1
    prior = release_path.read_bytes()
    assert len(approvals) == 1

    connection = sqlite3.connect(opts["authority_db"], isolation_level=None)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        with patch.object(
            SQLiteIdentityAuthorityStore, "__init__",
            side_effect=AssertionError("do not initialize shared authority schema"),
        ):
            assert consume_mobile_release_decisions(**opts) == 0
    finally:
        connection.rollback()
        connection.close()
    assert len(approvals) == 1
    assert release_path.read_bytes() == prior


def test_host_signed_decision_identity_verification_is_read_only(tmp_path):
    """New signed owner evidence is verified without any shared-DB schema write."""
    import hashlib
    from unittest.mock import patch
    from kernel.identity_authority import SQLiteIdentityAuthorityStore
    from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True,
    )
    flow.handle(**args)
    authority_before = hashlib.sha256(opts["authority_db"].read_bytes()).hexdigest()
    binding_before = hashlib.sha256(opts["bindings_db"].read_bytes()).hexdigest()
    approvals = []
    opts["approve_release"] = lambda *a, **kw: approvals.append(kw)
    with (
        patch.object(
            SQLiteIdentityAuthorityStore, "__init__",
            side_effect=AssertionError("schema must never be initialized from host reader"),
        ),
        patch.object(
            SQLiteMicrosoftIdentityBindingStore, "__init__",
            side_effect=AssertionError("binding migration must never run from host reader"),
        ),
    ):
        assert consume_mobile_release_decisions(**opts) == 1
    assert len(approvals) == 1
    assert hashlib.sha256(opts["authority_db"].read_bytes()).hexdigest() == authority_before
    assert hashlib.sha256(opts["bindings_db"].read_bytes()).hexdigest() == binding_before
    assert json.loads((opts["ccc_root"] / "material-review.json").read_text())[
        "source_revision"
    ] == SHA


def test_locked_unprocessed_authority_blocks_only_signed_consumer_until_retry(tmp_path):
    """Do not turn SQLITE_BUSY into owner consent, and never lose the pending proof."""
    import sqlite3
    from release_mobile_approval_consumer import MobileReleaseEvidenceBusy
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True,
    )
    flow.handle(**args)
    approvals = []
    opts["approve_release"] = lambda *a, **kw: approvals.append(kw)
    connection = sqlite3.connect(opts["authority_db"], isolation_level=None)
    try:
        connection.execute("BEGIN EXCLUSIVE")
        with pytest.raises(MobileReleaseEvidenceBusy, match="identity evidence database busy"):
            consume_mobile_release_decisions(**opts)
        assert approvals == []
        assert not (opts["ccc_root"] / "material-review.json").exists()
        assert not (
            opts["state_root"] / "mobile-release-decisions-processed"
            / (request.approval_id + ".json")
        ).exists()
    finally:
        connection.rollback()
        connection.close()
    assert consume_mobile_release_decisions(**opts) == 1
    assert len(approvals) == 1
    assert consume_mobile_release_decisions(**opts) == 0


def test_pending_owner_evidence_missing_identity_database_is_hard_error(tmp_path):
    import sqlite3
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    opts["authority_db"] = tmp_path / "missing-authority.sqlite3"
    approvals = []
    opts["approve_release"] = lambda *a, **kw: approvals.append(kw)
    with pytest.raises(sqlite3.OperationalError, match="unable to open database"):
        consume_mobile_release_decisions(**opts)
    assert not opts["authority_db"].exists()
    assert approvals == []
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_processed_mobile_marker_evidence_conflict_fails_before_identity_access(tmp_path):
    from unittest.mock import patch
    from kernel.identity_authority import SQLiteIdentityAuthorityStore
    flow, repo, release_path, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    opts["approve_release"] = lambda *a, **kw: None
    assert consume_mobile_release_decisions(**opts) == 1
    marker = (
        opts["state_root"] / "mobile-release-decisions-processed"
        / (request.approval_id + ".json")
    )
    stored = json.loads(marker.read_text())
    stored["signed_evidence_sha256"] = "tampered"
    marker.write_text(json.dumps(stored))
    with patch.object(
        SQLiteIdentityAuthorityStore, "__init__",
        side_effect=AssertionError("unnecessary shared DB access"),
    ):
        with pytest.raises(PermissionError, match="conflicting evidence"):
            consume_mobile_release_decisions(**opts)


def test_bounded_signed_evidence_ledger_busy_is_retryable_and_never_mints_authority(tmp_path):
    # The fixture ledger uses WAL where a separate EXCLUSIVE writer does not
    # necessarily block snapshots. Inject a real SQLite BUSY error code at
    # its one read-only open boundary to exercise the exact error handling.
    import sqlite3
    from unittest.mock import patch
    from release_mobile_approval_consumer import MobileReleaseEvidenceBusy
    flow, repo, record, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    invoked = []
    opts["approve_release"] = lambda *a, **kw: invoked.append(kw)
    busy = sqlite3.OperationalError("database is locked")
    busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
    with patch("release_mobile_approval_consumer._read_only_db", side_effect=busy):
        with pytest.raises(MobileReleaseEvidenceBusy, match="decision ledger busy"):
            consume_mobile_release_decisions(**opts)
    assert invoked == []
    assert not (opts["ccc_root"] / "material-review.json").exists()
    assert consume_mobile_release_decisions(**opts) == 1
    assert len(invoked) == 1


def test_locked_owner_binding_is_retryable_without_minting_release(tmp_path):
    import sqlite3
    from release_mobile_approval_consumer import MobileReleaseEvidenceBusy
    flow, repo, record, request, args, opts, identities, bindings = fixture(tmp_path)
    flow.handle(**args)
    invoked = []
    opts["approve_release"] = lambda *a, **kw: invoked.append(kw)
    lock = sqlite3.connect(opts["bindings_db"], isolation_level=None)
    try:
        lock.execute("BEGIN EXCLUSIVE")
        with pytest.raises(MobileReleaseEvidenceBusy, match="binding evidence database busy"):
            consume_mobile_release_decisions(**opts)
        assert invoked == []
        assert not (opts["ccc_root"] / "material-review.json").exists()
    finally:
        lock.rollback()
        lock.close()
    assert consume_mobile_release_decisions(**opts) == 1
    assert len(invoked) == 1

def test_high_impact_review_only_signed_teams_click_mints_ccc_not_release(tmp_path):
    """An already exact-approved core release can get a new mobile CCC review."""
    flow, repo, release_path, req, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, review_only=True,
    )
    before = release_path.read_bytes()
    assert req.metadata["review_only"] is True
    assert "CCC Material Review:" in req.presentation.title
    assert "ONLY the missing CCC" in req.presentation.summary
    assert req.requested_mode == "release:" + SHA

    accepted = flow.handle(**args)
    assert accepted["approval_status"] == "approved"
    assert release_path.read_bytes() == before
    calls = []
    opts["approve_release"] = lambda *a, **k: calls.append(k)
    assert consume_mobile_release_decisions(**opts) == 1
    assert calls == []
    assert release_path.read_bytes() == before
    material = json.loads((opts["ccc_root"] / "material-review.json").read_text())
    assert material["source_revision"] == SHA
    assert material["recorded_by"] == "person-al"
    assert material["mobile_approval_id"] == req.approval_id
    assert material["signed_evidence_sha256"] == repo.accepted_decision(
        req.approval_id
    ).authentication_evidence_hash
    assert consume_mobile_release_decisions(**opts) == 0
    marker = json.loads((opts["state_root"] / "mobile-release-decisions-processed"
                         / (req.approval_id + ".json")).read_text())
    assert marker["review_only"] is True


def test_high_impact_review_only_teams_deny_preserves_release_grant(tmp_path):
    flow, repo, release_path, req, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, review_only=True, approve=False,
    )
    original = release_path.read_bytes()
    response = flow.handle(**args)
    assert response["approval_status"] == "denied"
    opts["approve_release"] = lambda *a, **k: pytest.fail("deny cannot mint a release")
    assert consume_mobile_release_decisions(**opts) == 0
    assert release_path.read_bytes() == original
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_review_only_rejects_changed_previous_owner_sha_at_signed_callback(tmp_path):
    flow, repo, release_path, req, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, review_only=True,
    )
    record = json.loads(release_path.read_text())
    record["owner_approval"]["candidate_sha"] = ROLLBACK
    release_path.write_text(json.dumps(record))
    with pytest.raises(PermissionError, match="exact CCC-only card"):
        flow.handle(**args)
    assert repo.accepted_decision(req.approval_id) is None
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_review_only_rejects_modified_manifest_in_independent_host(tmp_path):
    flow, repo, release_path, req, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, review_only=True,
    )
    flow.handle(**args)
    record = json.loads(release_path.read_text())
    record["release_manifest"]["changed_files"].append("unreviewed_new_auth_file.py")
    release_path.write_text(json.dumps(record))
    opts["approve_release"] = lambda *a, **k: pytest.fail("tamper cannot mint release")
    with pytest.raises(PermissionError, match="exact prior owner release grant"):
        consume_mobile_release_decisions(**opts)
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_review_only_rejects_missing_prior_grant_in_independent_host(tmp_path):
    flow, repo, release_path, req, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, review_only=True,
    )
    flow.handle(**args)
    record = json.loads(release_path.read_text())
    record["owner_approval"]["approved"] = False
    release_path.write_text(json.dumps(record))
    opts["approve_release"] = lambda *a, **k: pytest.fail("no CCC-only backdoor")
    with pytest.raises(PermissionError, match="exact prior owner release grant"):
        consume_mobile_release_decisions(**opts)
    assert not (opts["ccc_root"] / "material-review.json").exists()


def test_review_only_signed_teams_replay_with_different_card_challenge_denied(tmp_path):
    flow, repo, release_path, req, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, review_only=True,
        card_selection_override={"card_challenge": "0" * 48},
    )
    with pytest.raises(PermissionError, match="card"):
        flow.handle(**args)
    assert repo.accepted_decision(req.approval_id) is None


def test_review_only_preexisting_different_signed_ccc_review_is_not_overwritten(tmp_path):
    flow, repo, release_path, req, args, opts, identities, bindings = fixture(
        tmp_path, reviewed=True, review_only=True,
    )
    flow.handle(**args)
    named = opts["ccc_root"] / ("material-review-" + SHA[:16] + ".json")
    prior = {"source_revision": SHA, "recorded_by": "person-al", "status": "approved",
             "signed_evidence_sha256": "0" * 64, "mobile_approval_id": "relapproval-old"}
    named.write_text(json.dumps(prior))
    opts["approve_release"] = lambda *a, **k: pytest.fail("no duplicate grant")
    with pytest.raises(PermissionError, match="conflicts with an existing owner review"):
        consume_mobile_release_decisions(**opts)
    assert json.loads(named.read_text()) == prior
    assert not (opts["ccc_root"] / "material-review.json").exists()
