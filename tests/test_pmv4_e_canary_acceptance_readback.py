"""Independent ROOT acceptance readback of a successful signed native canary.

Synthetic only: fixture root paths, Ed25519 keys and Docker return zero output.
No live files, services, approvals or external provider calls are affected.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
import stat
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from tools import pmv4_e_canary_acceptance_readback as a
from tools import pmv4_e_canary_contract as contract
from tools import independent_component_release as core
from implementation.kernel import signed_owner_release as signer


@pytest.fixture
def evidence(tmp_path,monkeypatch):
    now=datetime.now(timezone.utc)
    issued=now-timedelta(minutes=4)
    journal_time=now-timedelta(minutes=3)
    private=Ed25519PrivateKey.generate()
    oid=next(iter(signer.EXACT_OWNER_OAUTH_SUBJECTS))
    sig=signer.issue_exact_owner_release(
        approval_id=a.APPROVAL_ID,
        release_id="release-"+a.SOURCE[:16],
        candidate_sha=a.SOURCE,rollback_sha="0"*40,
        scope_sha256=a.SCOPE,manifest_sha256=a.MANIFEST,
        freeze_sha256=a.FREEZE,
        verified_tenant_id=signer.TID,
        verified_owner_oid=oid,
        verified_principal=signer.EXACT_OWNER_OAUTH_SUBJECTS[oid],
        verified_organization_id="aot",
        confirmed_decision="approve",at=issued,private_key=private,
    )
    mock_signer=SimpleNamespace(
        verify_exact_owner_release=signer.verify_exact_owner_release,
        read_pinned_root_owner_public_key=lambda *_:private.public_key(),
    )
    monkeypatch.setattr(a,"signer_module",lambda:mock_signer)
    paths={
        "terminal":tmp_path/"control/accepted.json",
        "started":tmp_path/"control/started.json",
        "native":tmp_path/"receipts/owner.json",
        "bundle":tmp_path/"releases/manifest.json",
        "freeze":tmp_path/"freeze-marker",
        "policy":tmp_path/"protected-policy",
        "active":tmp_path/"active/pmv4-e-canary.json",
    }
    for p in paths.values():p.parent.mkdir(parents=True,exist_ok=True)
    # Generate the exact real reviewed candidate manifest from checked-in
    # Compose/config, rather than constructing a pretend release identity.
    root=Path(__file__).resolve().parents[1]
    compose=(root/"infrastructure/pmv4-e-canary/compose.yaml").read_bytes()
    config=(root/"infrastructure/pmv4-e-canary/config.json").read_bytes()
    manifest=contract.manifest(
        compose=compose,config=config,
        freeze_sha256=a.FREEZE,candidate_sha=a.SOURCE)
    assert sha256(core.canonical(manifest)).hexdigest()==a.MANIFEST
    assert manifest["scope_sha256"]==a.SCOPE

    records={
        "terminal":{
            "schema_version":"1.0","state":"accepted_and_removed",
            "action":a.ACTION,"source_sha":a.SOURCE,"build_sha":a.BUILD,
            "approval_id":a.APPROVAL_ID,"scope_sha256":a.SCOPE,
            "manifest_sha256":a.MANIFEST,
            "native_generic_acceptance_verified":True,
            "isolated_canary_rollback_verified":True,
            "protected_before_equals_after":True,
            "production_freeze_unchanged":True,"provider_calls":0,
            "pmv3_units_modified":False,"retirement_authorized":False,
            "protected_policy_sha256":a.POLICY,
        },
        "started":{
            "schema_version":"1.0","state":"started","action":a.ACTION,
            "source_sha":a.SOURCE,"build_sha":a.BUILD,
            "owner_approval_id":a.APPROVAL_ID,
            "scope_sha256":a.SCOPE,"manifest_sha256":a.MANIFEST,
            "protected_before":{
                "jason-runtime":["id","image","start"],
                "jason-pmv4-ticket-core":["id","image","start"],
                "jason-mcp-pilot":["id","image","start"],
                "jason-pmv4-shadow-gateway":["id","image","start"],
                "jason-teams-gateway":["id","image","start"],
                "openbao":["id","image","start"],
            },
        },
        "native":{
            "schema_version":"1.0","state":"accepted",
            "component_id":"pmv4-e-canary",
            "candidate_sha":a.SOURCE,"rollback_sha":"0"*40,
            "approval_id":a.APPROVAL_ID,
            "release_id":"release-"+a.SOURCE[:16],
            "scope_sha256":a.SCOPE,"manifest_sha256":a.MANIFEST,
            "freeze_sha256":a.FREEZE,
            "started_at":journal_time.isoformat(),
            "signed_owner_proof":sig,
        },
        "bundle":manifest,
    }
    for k,v in records.items():
        paths[k].write_bytes(json.dumps(v,sort_keys=True,
            separators=(",",":")).encode())
        paths[k].chmod(0o444 if k=="bundle" else 0o600)
    paths["freeze"].write_bytes(b"test freeze marker")
    paths["policy"].write_bytes(b"test desired state")
    paths["freeze"].chmod(0o600)
    paths["policy"].chmod(0o600)
    # Synthetic file contents cannot reproduce approved SHA-256 preimages.
    # Keep all protected signer, manifest, receipt and policy constants intact.
    # The live-probe fixture passes only the two fake file digests explicitly.
    monkeypatch.setattr(a,"TERMINAL",paths["terminal"])
    monkeypatch.setattr(a,"STARTED",paths["started"])
    monkeypatch.setattr(a,"NATIVE",paths["native"])
    monkeypatch.setattr(a,"BUNDLE",paths["bundle"])
    monkeypatch.setattr(a,"ACTIVE",paths["active"])
    monkeypatch.setattr(a,"FREEZE_PATH",paths["freeze"])
    monkeypatch.setattr(a,"POLICY_PATH",paths["policy"])
    monkeypatch.setattr(a.historical,"inspect",lambda:{
        "status":"pre_retirement_root_acceptance_verified"})
    monkeypatch.setattr(a.os,"geteuid",lambda:0)
    original_lstat=Path.lstat
    files={p for k,p in paths.items() if k!="active"}
    def fake_lstat(path):
        orig=original_lstat(path)
        if path in files:
            return SimpleNamespace(st_mode=orig.st_mode,st_uid=0,st_gid=0,
                 st_nlink=orig.st_nlink,st_size=orig.st_size)
        return orig
    monkeypatch.setattr(Path,"lstat",fake_lstat)
    return paths,records,private


def test_root_terminal_native_acceptance_with_real_signed_owner_proof(evidence):
    paths,records,key=evidence
    result=a.exact_receipts()
    assert result["owner_signature_verified_at_native_start"] is True
    assert result["native_journal_state"]=="accepted"
    assert result["root_terminal_state"]=="accepted_and_removed"
    assert result["historical_protected_count"]==6
    assert result["approval_id"]==a.APPROVAL_ID


@pytest.mark.parametrize("document,field,bad,reason",[
    ("terminal","state","started","FINAL_CANARY_ACCEPTANCE_RECEIPT_NOT_EXACT"),
    ("terminal","isolated_canary_rollback_verified",False,"FINAL_CANARY_ACCEPTANCE_RECEIPT_NOT_EXACT"),
    ("terminal","pmv3_units_modified",True,"FINAL_CANARY_ACCEPTANCE_RECEIPT_NOT_EXACT"),
    ("terminal","retirement_authorized",True,"FINAL_CANARY_ACCEPTANCE_RECEIPT_NOT_EXACT"),
    ("native","state","rolled_back","NATIVE_SIGNED_ACCEPTANCE_JOURNAL_NOT_EXACT"),
    ("native","approval_id","owner-mcp-"+"f"*32,"NATIVE_SIGNED_ACCEPTANCE_JOURNAL_NOT_EXACT"),
    ("native","scope_sha256","a"*64,"NATIVE_SIGNED_ACCEPTANCE_JOURNAL_NOT_EXACT"),
    ("started","source_sha","0"*40,"INITIAL_CANARY_ROOT_TRANSACTION_NOT_EXACT"),
    ("bundle","candidate_sha","0"*40,"ROOT_CANARY_MANIFEST_NOT_EXACT"),
])
def test_mutated_root_receipts_never_confer_parity(evidence,document,field,bad,reason):
    paths,_,_=evidence
    doc=json.loads(paths[document].read_bytes());doc[field]=bad
    paths[document].chmod(0o600)
    paths[document].write_bytes(json.dumps(doc).encode())
    paths[document].chmod(0o444 if document=="bundle" else 0o600)
    with pytest.raises(a.CanaryAcceptanceDenied,match=reason):
        a.exact_receipts()


def test_invalid_owner_signature_is_not_revalidated_as_historical_approval(evidence):
    paths,_,_=evidence
    doc=json.loads(paths["native"].read_bytes())
    doc["signed_owner_proof"]["payload"]["decision"]="deny"
    paths["native"].write_bytes(json.dumps(doc).encode())
    with pytest.raises(a.CanaryAcceptanceDenied,match="NATIVE_OWNER_SIGNATURE_NOT_VERIFIED"):
        a.exact_receipts()


def test_independent_signer_expiration_is_checked_against_original_start_time(evidence):
    paths,_,_=evidence
    doc=json.loads(paths["native"].read_bytes())
    doc["started_at"]=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    paths["native"].write_bytes(json.dumps(doc).encode())
    with pytest.raises(a.CanaryAcceptanceDenied,match="NATIVE_START_TIME_NOT_HISTORIC"):
        a.exact_receipts()


def test_missing_root_receipt_fails_closed(evidence):
    paths,_,_=evidence
    paths["native"].unlink()
    with pytest.raises(a.CanaryAcceptanceDenied,match="ROOT_FILE_UNAVAILABLE"):
        a.exact_receipts()


def test_root_permission_violation_fails_closed(evidence):
    paths,_,_=evidence
    paths["native"].chmod(0o644)
    with pytest.raises(a.CanaryAcceptanceDenied,match="ROOT_FILE_UNTRUSTED"):
        a.exact_receipts()


def test_live_root_cleanup_probe_is_readonly_and_exact(evidence):
    paths,_,_=evidence
    seen=[]
    def mock_run(argv,**kw):
        seen.append(tuple(argv))
        return SimpleNamespace(returncode=0,stdout="")
    result=a.probe_clean_host(
        runner=mock_run,
        expected_freeze_sha=sha256(paths["freeze"].read_bytes()).hexdigest(),
        expected_policy_sha=sha256(paths["policy"].read_bytes()).hexdigest())
    assert result["canary_container_absent"]
    assert result["canary_network_absent"]
    assert result["active_pointer_absent"]
    assert result["freeze_sha256"]==sha256(
        paths["freeze"].read_bytes()).hexdigest()
    assert len(seen)==2
    assert all(cmd[:2]==("/usr/bin/docker",verb) for cmd,verb in
               zip(seen,("ps","network")))
    assert not any(x in " ".join(c) for c in seen for x in
                   ("stop","rm ","network rm","systemctl","disable"))


def test_live_probe_rejects_unremoved_canary_container(evidence):
    paths,_,_=evidence
    def unsafe(argv,**kw):
        return SimpleNamespace(returncode=0,stdout="canary-container-id\n")
    with pytest.raises(a.CanaryAcceptanceDenied,match="PRIVATE_CANARY_STILL_PRESENT"):
        a.probe_clean_host(
            runner=unsafe,
            expected_freeze_sha=sha256(paths["freeze"].read_bytes()).hexdigest(),
            expected_policy_sha=sha256(paths["policy"].read_bytes()).hexdigest())


def test_live_probe_rejects_unremoved_active_pointer(evidence):
    paths,_,_=evidence
    paths["active"].write_text("not a removed canary")
    def none(argv,**kw):
        return SimpleNamespace(returncode=0,stdout="")
    with pytest.raises(a.CanaryAcceptanceDenied,match="ACTIVE_POINTER_NOT_REMOVED"):
        a.probe_clean_host(
            runner=none,
            expected_freeze_sha=sha256(paths["freeze"].read_bytes()).hexdigest(),
            expected_policy_sha=sha256(paths["policy"].read_bytes()).hexdigest())


def test_top_level_root_readback_does_not_claim_retirement(evidence,monkeypatch):
    paths,_,_=evidence
    def mock_run(argv,**kw):
        return SimpleNamespace(returncode=0,stdout="")
    import subprocess
    original_run=subprocess.run
    monkeypatch.setattr(a.subprocess,"run",mock_run)
    actual=a.probe_clean_host
    monkeypatch.setattr(a,"probe_clean_host",lambda:actual(
        runner=mock_run,
        expected_freeze_sha=sha256(paths["freeze"].read_bytes()).hexdigest(),
        expected_policy_sha=sha256(paths["policy"].read_bytes()).hexdigest()))
    result=a.inspect()
    assert result["status"]=="native_providerfree_canary_accepted_and_removed"
    assert result["pmv3_retirement_authorized"] is False
    assert result["replacement_scheduler_parity_accepted"] is False
    assert result["production_mutations"] is False
    assert result["stage_c_d_a1_root_acceptance"] is True


def test_unprivileged_runner_must_not_claim_root_attestation(evidence,monkeypatch):
    monkeypatch.setattr(a.os,"geteuid",lambda:1000)
    with pytest.raises(a.CanaryAcceptanceDenied,match="ROOT_ONLY"):
        a.inspect()


def test_root_readback_has_no_mutating_calls():
    source=Path(a.__file__).read_text()
    for text in ("systemctl stop","systemctl disable","docker rm",
                 "docker start","os.replace(","os.chown(","os.chmod(",
                 "subprocess.check_call(","delete(", "force_close_breaker"):
        assert text not in source
    assert '"pmv3_retirement_authorized":False' in source
    assert '"production_mutations":False' in source



def test_pinned_readonly_signer_matches_reviewed_source():
    root=Path(__file__).resolve().parents[1]
    source=(root/"implementation/kernel/signed_owner_release.py").read_bytes()
    assert sha256(source).hexdigest()==a.ROOT_SIGNER_SHA


def test_manifest_contract_is_byte_exact_sha_against_original_canary():
    root=Path(__file__).resolve().parents[1]
    manifest=contract.manifest(
        compose=(root/"infrastructure/pmv4-e-canary/compose.yaml").read_bytes(),
        config=(root/"infrastructure/pmv4-e-canary/config.json").read_bytes(),
        freeze_sha256=a.FREEZE,candidate_sha=a.SOURCE)
    assert manifest["scope_sha256"]==a.SCOPE
    assert sha256(core.canonical(manifest)).hexdigest()==a.MANIFEST
    assert manifest["provider_scope"]["provider"]=="none"
    assert manifest["rollback_sha"]=="0"*40
