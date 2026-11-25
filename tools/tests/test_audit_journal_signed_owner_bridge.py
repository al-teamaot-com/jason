"""Signed exact Owner offer => independent Root audit adoption contract tests."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tools import audit_journal_signed_owner_bridge as bridge
from jason_mcp import audit_journal_adoption_approval as issuer
from kernel import signed_owner_release as signed

CANDIDATE="a"*40
ROOT_GATE={"breaker":"closed","drift":"pass","peers_verified":True,
           "mount_verified":True,"dataset_identity":{"device":3,"inode":7}}
OWNER_PRINCIPAL="person-entra-bee80bdcffb04c50b453c09d4d411f5f"
CLAIMS={"tid":bridge.TENANT,"oid":bridge.OWNER}

def reviewed_scope(candidate=CANDIDATE):
    return {
       "action":bridge.ACTION,
       "policy":{"candidate_sha":candidate,"rollback_sha":bridge.ROLLBACK},
       "dataset_identity":{"device":3,"inode":7},
       "installation_targets":["/srv/jason/archive/governed-audit/orchestration"],
       "protected_peers":{"jason-runtime":"healthy"},
    }

def test_manifest_one_transaction_freeze_remains_active():
    s=reviewed_scope();m=bridge.manifest(s,CANDIDATE,"1"*64,ROOT_GATE)
    assert m["provider_mutations"] is False
    assert m["standing_authority"] is False
    assert m["one_use"] is True
    assert m["availability_interruption_authorized"] is True
    assert m["freeze_sha256"]=="1"*64
    assert m["scope_sha256"]==bridge.digest(bridge.canon(s))
    assert m["archive_root"]==bridge.ARCHIVE

@pytest.mark.parametrize("mutation",[
    lambda s:s.update(action="full_source_release"),
    lambda s:s.update(policy={}),
    lambda s:s["policy"].update(rollback_sha="0"*40),
    lambda s:s["policy"].update(candidate_sha="f"*40),
])
def test_wrong_scope_refuses_root_offer(mutation):
    s=reviewed_scope();mutation(s)
    with pytest.raises(bridge.ArchiveOwnerDenied):
        bridge.manifest(s,CANDIDATE,"1"*64,ROOT_GATE)

@pytest.mark.parametrize("mutation",[
    lambda gate:gate.update(breaker="open"),
    lambda gate:gate.update(drift="drift_detected"),
    lambda gate:gate.update(peers_verified=False),
    lambda gate:gate.update(mount_verified=False),
])
def test_root_stage_refuses_unhealthy_state(mutation):
    gate=dict(ROOT_GATE);mutation(gate)
    with pytest.raises(bridge.ArchiveOwnerDenied):
        bridge.manifest(reviewed_scope(),CANDIDATE,"1"*64,gate)

def stage_and_sign(tmp_path,monkeypatch):
    folder=tmp_path/"authority"
    folder.mkdir(mode=0o700)
    stage_folder=tmp_path/"stage"
    stage_folder.mkdir(mode=0o700)
    for child in ("offers","owner-approvals"):
        (folder/child).mkdir(mode=0o700)
    monkeypatch.setattr(bridge,"STAGED",stage_folder)
    monkeypatch.setattr(bridge,"PUBLIC",folder)
    monkeypatch.setattr(bridge,"freeze_proof",lambda:"f"*64)
    monkeypatch.setattr(bridge,"stage_directories_once",lambda:None)
    monkeypatch.setattr(bridge,"verified_public_dir",lambda *args,**kw:None)
    monkeypatch.setattr(bridge.os,"geteuid",lambda:0)
    # Simulated Root staging filesystem; real owner/mode checks use isolated
    # UID0 fixture and still run independently of this contract test.
    def simulated_exclusive(path,raw,owner,mode):
        if path.exists() or path.is_symlink():
            bridge.need(False,"ONE_USE_RECORD_ALREADY_EXISTS")
        path.write_bytes(raw)
        path.chmod(mode)
    monkeypatch.setattr(bridge,"exclusive",simulated_exclusive)
    scope=reviewed_scope()
    offer=bridge.create_staged_offer(scope,CANDIDATE,ROOT_GATE)
    signer=Ed25519PrivateKey.generate()
    # The issuer is UID1000 in production. GitHub-hosted runners use a
    # different UID, so these synthetic temp files belong to the runner's
    # actual UID; the separate isolated UID0/UID1000 fixture tests custody.
    synthetic_unprivileged_uid=os.getuid()
    monkeypatch.setattr(issuer.os,"geteuid",lambda:synthetic_unprivileged_uid)
    monkeypatch.setattr(issuer,"read_offer",
        lambda state,release_id:offer)
    row=issuer.queue_exact_archive_owner_approval(
        state_root=folder,release_id=offer["release_id"],
        candidate_sha=CANDIDATE,scope_sha256=offer["scope_sha256"],
        manifest_sha256=offer["manifest_sha256"],
        approved_by=OWNER_PRINCIPAL,organization_id="aot",
        verified_token_claims=CLAIMS,service_signer=signer,
        affirmative_decision=issuer.APPROVAL_WORDS,
    )
    assert row["status"]=="signed_exact_owner_approval_queued_not_deployed"
    monkeypatch.setattr(bridge.os,"geteuid",lambda:0)
    # Avoid importing any service key or fixture private key into trust:
    # this mock supplies only the public key to the genuine Ed25519 verifier.
    monkeypatch.setattr(signed,"read_pinned_root_owner_public_key",
        lambda path:signer.public_key())
    # Unprivileged test cannot create root-owned files. The real Root UID
    # custody fixture covers metadata, while this test covers signature.
    monkeypatch.setattr(bridge,"private_json",
        lambda path,owner,mode,maximum=1_000_000:json.loads(path.read_bytes()))
    return offer,scope,signer,folder,stage_folder

def test_full_real_ed25519_handoff_and_same_scope_exact_one_use(tmp_path,monkeypatch):
    offer,scope,signer,public,staged=stage_and_sign(tmp_path,monkeypatch)
    evidence=bridge.verify_previously_signed_root_offer(
        scope,CANDIDATE,ROOT_GATE)
    assert evidence["approval_id"].startswith("owner-mcp-")
    assert evidence["same_scope_recheck_passed"] is True
    assert evidence["new_global_unfreeze"] is False
    assert evidence["standalone_archive_only"] is True
    assert evidence["signed_owner_proof_sha256"]==bridge.digest(bridge.canon(
        json.loads((public/"owner-approvals"/
            (offer["release_id"]+".json")).read_bytes())["signed_owner_proof"]))
    consume=bridge.consume_one_use(CANDIDATE,evidence)
    assert consume.is_file()
    assert json.loads(consume.read_bytes())["approval_id"]==evidence["approval_id"]
    with pytest.raises(bridge.ArchiveOwnerDenied,match="SIGNED_OWNER_APPROVAL_CONSUMED"):
        bridge.verify_previously_signed_root_offer(scope,CANDIDATE,ROOT_GATE)
    with pytest.raises(bridge.ArchiveOwnerDenied,match="ONE_USE_RECORD_ALREADY_EXISTS"):
        bridge.consume_one_use(CANDIDATE,evidence)

@pytest.mark.parametrize("tamper",[
    "modified_public_offer","modified_root_stage","modified_signature",
    "modified_public_signed_fields","another_lkg","another_inode",
    "invalid_owner_principal","invalid_action","no_pinned_key",
    "stale_stage","future_stage",
])
def test_wrong_signed_offer_or_root_evidence_fails_closed(
        tmp_path,monkeypatch,tamper):
    offer,scope,signer,public,staged=stage_and_sign(tmp_path,monkeypatch)
    o=public/"offers"/(offer["release_id"]+".json")
    r=staged/(offer["release_id"]+".json")
    a=public/"owner-approvals"/(offer["release_id"]+".json")
    if tamper=="modified_public_offer":
        row=json.loads(o.read_bytes());row["freeze_sha256"]="a"*64;o.write_bytes(bridge.canon(row))
    elif tamper=="modified_root_stage":
        row=json.loads(r.read_bytes());row["owner_oid"]="foreign";r.chmod(0o600);r.write_bytes(bridge.canon(row))
    elif tamper=="modified_signature":
        row=json.loads(a.read_bytes());row["signed_owner_proof"]["payload"]["scope_sha256"]="1"*64
        a.write_bytes(bridge.canon(row))
    elif tamper=="modified_public_signed_fields":
        row=json.loads(a.read_bytes());row["root_stage_receipt_sha256"]="0"*64
        a.write_bytes(bridge.canon(row))
    elif tamper=="another_lkg":scope["policy"]["rollback_sha"]="1"*40
    elif tamper=="another_inode":scope["dataset_identity"]["inode"]=13
    elif tamper=="invalid_owner_principal":
        row=json.loads(a.read_bytes());row["signed_owner_proof"]["payload"]["owner_oid"]="x"
        a.write_bytes(bridge.canon(row))
    elif tamper=="invalid_action":
        row=json.loads(a.read_bytes());row["action"]="source_release";a.write_bytes(bridge.canon(row))
    elif tamper=="no_pinned_key":
        monkeypatch.setattr(signed,"read_pinned_root_owner_public_key",
            lambda path:(_ for _ in ()).throw(
                signed.OwnerReleaseProofDenied("MISSING_ROOT_KEY")))
    else:
        row=json.loads(r.read_bytes())
        row["staged_at"]=(datetime.now(timezone.utc)+timedelta(minutes=
                           -14 if tamper=="stale_stage" else 14)).isoformat()
        r.chmod(0o600)
        r.write_bytes(bridge.canon(row))
    with pytest.raises((bridge.ArchiveOwnerDenied,signed.OwnerReleaseProofDenied)):
        bridge.verify_previously_signed_root_offer(scope,CANDIDATE,ROOT_GATE)
    assert not (staged/(offer["release_id"]+".consumed.json")).exists()

@pytest.mark.parametrize("bad_record", [
    "wrong_mode","symlink","wrong_size","nlink",
])
def test_private_file_validates_custody(tmp_path,bad_record):
    p=tmp_path/"record"
    p.write_bytes(b"trusted record")
    p.chmod(0o600)
    owner=p.stat().st_uid
    if bad_record=="wrong_mode":
        p.chmod(0o666)
    elif bad_record=="symlink":
        q=tmp_path/"other";p.rename(q);p.symlink_to(q)
    elif bad_record=="wrong_size":
        p.write_bytes(b"")
    elif bad_record=="nlink":
        (tmp_path/"linked").hardlink_to(p)
    with pytest.raises(bridge.ArchiveOwnerDenied):
        bridge.private_file(p,owner,0o600)

def test_signed_mcp_source_never_claims_to_deploy():
    source=Path(issuer.__file__).read_text()
    assert "sudo" not in source
    assert "systemctl" not in source
    assert "docker" not in source
    assert "available" not in source or "Root" in source
    assert "verify_exact_owner_release" in source
    assert "O_EXCL" in source


def test_existing_owner_signature_remains_usable_after_stage_offer_ttl(
        tmp_path,monkeypatch):
    """A queued native Root service need not demand a SECOND Owner approval."""
    base=datetime.now(timezone.utc)
    class Clock(datetime):
        stage_offset_minutes=-8
        @classmethod
        def now(cls,tz=None):
            result=base+timedelta(minutes=cls.stage_offset_minutes)
            return result.astimezone(tz) if tz else result.replace(tzinfo=None)
    monkeypatch.setattr(bridge,"datetime",Clock)
    # Root stages eight minutes before the licensed Owner signs.
    offer,scope,signer,public,staged=stage_and_sign(tmp_path,monkeypatch)
    # The signed 15-minute proof is still valid four minutes after signing,
    # even though the ten-minute *offer* window has already ended.
    Clock.stage_offset_minutes=4
    evidence=bridge.verify_previously_signed_root_offer(
        scope,CANDIDATE,ROOT_GATE)
    assert evidence["approval_id"].startswith("owner-mcp-")
    assert evidence["same_scope_recheck_passed"] is True
    assert evidence["new_global_unfreeze"] is False


def test_owner_signature_created_after_stage_offer_window_is_denied(
        tmp_path,monkeypatch):
    """Even a mathematically valid signature cannot extend the initial offer."""
    base=datetime.now(timezone.utc)
    class Clock(datetime):
        stage_offset_minutes=-11
        @classmethod
        def now(cls,tz=None):
            result=base+timedelta(minutes=cls.stage_offset_minutes)
            return result.astimezone(tz) if tz else result.replace(tzinfo=None)
    # Stage is 11 minutes old. This helper intentionally signs a synthetic
    # offer without the real MCP read_offer() freshness check, to prove the
    # independent Root also rejects that invalid authorization timing.
    monkeypatch.setattr(bridge,"datetime",Clock)
    offer,scope,signer,public,staged=stage_and_sign(tmp_path,monkeypatch)
    Clock.stage_offset_minutes=1
    with pytest.raises(bridge.ArchiveOwnerDenied,
                       match="OWNER_SIGNATURE_OUTSIDE_ORIGINAL_OFFER_WINDOW"):
        bridge.verify_previously_signed_root_offer(
            scope,CANDIDATE,ROOT_GATE)
