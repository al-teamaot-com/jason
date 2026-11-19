"""Exact authenticated Owner bootstrap STARTED precedes sealed root staging."""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from pathlib import Path
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from tools import pmv4_e_signed_bootstrap_phase as bootstrap
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet
from tools.tests.test_pmv4_e_signed_native_ledger import (
    KEY,CANDIDATE,ROLLBACK,approval,
)

def fixtures(tmp_path):
    journal=tmp_path/"bootstrap"
    receipts=tmp_path/"native-receipts"
    journal.mkdir(mode=0o700)
    receipts.mkdir(mode=0o700)
    state={
        "host":True,"freeze":True,"old":True,"inert":True,
        "marker_absent":True,"ci":True,
    }
    instance=bootstrap.SignedInertBootstrap(
        root=journal,source_root=packet.ROOT,
        native_receipts=receipts,production=False,
        test_owner_public_key=KEY.public_key(),
        host_lock_held=lambda:state["host"],
        freeze_lock_held=lambda:state["freeze"],
        legacy_active=lambda:state["old"],
        replacements_inert=lambda:state["inert"],
        marker_absent=lambda:state["marker_absent"],
        source_ci_verified=lambda candidate:state["ci"]
                and candidate==CANDIDATE,
    )
    manifest=contract.draft(
        candidate_sha=CANDIDATE,rollback_sha=ROLLBACK)
    req={
        "schema_version":"1.0",
        "request_id":"release-"+CANDIDATE[:16],
        "action":bootstrap.BOOTSTRAP_ACTION,
        "candidate_sha":CANDIDATE,
        "rollback_sha":ROLLBACK,
        "scope_sha256":manifest["scope_sha256"],
        "manifest_sha256":manifest["manifest_sha256"],
        "freeze_sha256":manifest["manifest"]["freeze_sha256"],
        "signed_owner_proof":approval(manifest["manifest"]),
    }
    return instance,req,state,journal,receipts


def test_one_exact_grant_writes_only_bootstrap_started_not_systemd(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    before=b.validate(request)
    assert before["status"]=="owner_signed_inert_bootstrap_preflight_only"
    assert before["source_file_count"]==len(packet.REVIEWED_PATHS)
    assert list(root.iterdir())==[]
    started=b.begin(request)
    assert started["status"]=="bootstrap_started_no_systemd_mutation"
    assert started["native_systemd_release_authorized"] is False
    assert b.signed_started(
        candidate_sha=CANDIDATE,
        scope_sha256=request["scope_sha256"],
        approval_id=request["signed_owner_proof"]["payload"]["approval_id"])
    assert len(list(root.iterdir()))==1
    record=json.loads(next(root.iterdir()).read_text())
    assert record["recovery_required"] is True
    assert record["signed_owner_proof"]==request["signed_owner_proof"]
    assert record["no_unit_mutations"] is True
    assert record["native_systemd_release_authorized"] is False
    with pytest.raises(PermissionError,match="OWNER_RELEASE_ONE_USE_REPLAY"):
        b.begin(request)


@pytest.mark.parametrize("field,bad",[
    ("candidate_sha","a"*40),("rollback_sha",CANDIDATE),
    ("scope_sha256","0"*64),("manifest_sha256","0"*64),
    ("freeze_sha256","0"*64),("action","host_reconcile"),
    ("request_id","release-"+"a"*16),
])
def test_wrong_action_or_exact_release_scope_denied_without_root_journal(
        tmp_path,field,bad):
    b,request,state,root,_=fixtures(tmp_path)
    request[field]=bad
    with pytest.raises(PermissionError):
        b.begin(request)
    assert list(root.iterdir())==[]


@pytest.mark.parametrize("field",[
    "host","freeze","old","inert","marker_absent","ci",
])
def test_lock_live_state_and_protected_ci_gate_before_root_write(
        tmp_path,field):
    b,request,state,root,_=fixtures(tmp_path)
    state[field]=False
    with pytest.raises(PermissionError):
        b.begin(request)
    assert list(root.iterdir())==[]


def test_bad_expired_denied_owner_proof_leaves_no_bootstrap(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    request["signed_owner_proof"]=approval(
        contract.draft(candidate_sha=CANDIDATE,
                       rollback_sha=ROLLBACK)["manifest"],
        at=datetime.now(timezone.utc)-timedelta(minutes=20))
    with pytest.raises(PermissionError,match="OWNER_RELEASE_EXPIRED_OR_FUTURE"):
        b.begin(request)
    assert list(root.iterdir())==[]


def test_untrusted_signer_denied_before_root_write(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    request["signed_owner_proof"]=approval(
        contract.draft(candidate_sha=CANDIDATE,
                       rollback_sha=ROLLBACK)["manifest"],
        key=Ed25519PrivateKey.generate())
    with pytest.raises(PermissionError,match="SIGNATURE_INVALID"):
        b.begin(request)
    assert list(root.iterdir())==[]


def test_bootstrap_cannot_replay_native_approved_release(tmp_path):
    b,request,state,root,receipts=fixtures(tmp_path)
    signed_id=request["signed_owner_proof"]["payload"]["approval_id"]
    receipt=receipts/("owner-"+signed_id+".json")
    receipt.write_text(json.dumps({"approval_id":signed_id,"state":"accepted"}))
    receipt.chmod(0o600)
    with pytest.raises(PermissionError,match="ONE_USE_REPLAY"):
        b.begin(request)
    assert list(root.iterdir())==[]


def test_wrong_record_or_owner_id_cannot_unlock_stager(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    assert not b.signed_started(
        candidate_sha=CANDIDATE,scope_sha256=request["scope_sha256"],
        approval_id="owner-mcp-"+"a"*32)
    b.begin(request)
    signed_id=request["signed_owner_proof"]["payload"]["approval_id"]
    assert not b.signed_started(
        candidate_sha="c"*40,scope_sha256=request["scope_sha256"],
        approval_id=signed_id)
    assert not b.signed_started(
        candidate_sha=CANDIDATE,scope_sha256="f"*64,
        approval_id=signed_id)


def test_unreviewed_or_removed_request_field_denied(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    request["caller_sudo"]="yes"
    with pytest.raises(PermissionError):
        b.begin(request)
    del request["caller_sudo"]
    del request["signed_owner_proof"]
    with pytest.raises(PermissionError):
        b.begin(request)
    assert list(root.iterdir())==[]


def test_source_only_cannot_claim_production_root_install(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    with pytest.raises(bootstrap.StageEBootstrapDenied,
                       match="CANONICAL_ROOT_INSTALL_REQUIRED"):
        bootstrap.SignedInertBootstrap(
            root=tmp_path,source_root=packet.ROOT,
            host_lock_held=lambda:True,freeze_lock_held=lambda:True,
            legacy_active=lambda:True,replacements_inert=lambda:True,
            marker_absent=lambda:True,source_ci_verified=lambda _:True,
            production=True,
        )


def test_inert_stage_and_immutable_root_manifest_verify_same_owner_proof(
        tmp_path):
    from hashlib import sha256
    from tools import pmv4_e_root_trust_stage as trust
    from tools import pmv4_e_native_root_manifest_attestation as attestor
    b,request,state,root,receipts=fixtures(tmp_path)
    b.begin(request)
    owner_id=request["signed_owner_proof"]["payload"]["approval_id"]
    sealed=tmp_path/"sealed-root"
    stager=trust.RootTrustStager(
        source=packet.ROOT,target=sealed,
        native_signed_started=lambda:b.signed_started(
            candidate_sha=CANDIDATE,
            scope_sha256=request["scope_sha256"],
            approval_id=owner_id),
        native_host_locked=lambda:state["host"],
        native_freeze_locked=lambda:state["freeze"],
        native_marker_absent=lambda:state["marker_absent"],
        native_replacements_inert=lambda:state["inert"],
        production=False,
    )
    hashes={
        name:sha256((packet.ROOT/name).read_bytes()).hexdigest()
        for name in packet.REVIEWED_PATHS
    }
    result=stager.stage(source_sha=CANDIDATE,exact_hashes=hashes)
    assert result["installed_file_count"]==len(packet.REVIEWED_PATHS)
    release=tmp_path/"root-release"
    release.mkdir(mode=0o700)
    manifest=contract.draft(candidate_sha=CANDIDATE,
                            rollback_sha=ROLLBACK)
    for name,content in (
        ("manifest.json",manifest["manifest"]),
        ("source-scope.json",manifest["source_scope"]),
    ):
        p=release/name
        p.write_bytes(packet.canonical(content))
        p.chmod(0o444)
    release.chmod(0o555)
    witness=attestor.inspect(
        source_root=sealed,release_dir=release,production=False)
    assert witness["status"]=="root_source_attested_no_release_authority"
    assert witness["manifest_sha256"]==request["manifest_sha256"]
    assert not witness["release_authorized"]
    stager.recover_inert_stage(hashes)
    assert not sealed.exists()


def test_signed_started_rejects_corrupted_proof_even_from_root_receipt(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    b.begin(request)
    owner_id=request["signed_owner_proof"]["payload"]["approval_id"]
    path=root/("owner-"+owner_id+".json")
    original=path.read_bytes()
    row=json.loads(original)
    row["signed_owner_proof"]["signature_base64url"]="A"*86
    path.write_text(json.dumps(row))
    path.chmod(0o600)
    assert b.signed_started(
        candidate_sha=CANDIDATE,scope_sha256=request["scope_sha256"],
        approval_id=owner_id) is False


def test_signed_started_rejects_mismatched_proof_digest_even_if_signature_valid(tmp_path):
    b,request,state,root,_=fixtures(tmp_path)
    b.begin(request)
    owner_id=request["signed_owner_proof"]["payload"]["approval_id"]
    path=root/("owner-"+owner_id+".json")
    record=json.loads(path.read_text())
    record["signed_owner_proof_sha256"]="f"*64
    path.write_text(json.dumps(record))
    path.chmod(0o600)
    assert b.signed_started(
        candidate_sha=CANDIDATE,scope_sha256=request["scope_sha256"],
        approval_id=owner_id) is False
