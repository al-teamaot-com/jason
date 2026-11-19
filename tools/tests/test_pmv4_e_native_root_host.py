"""Native Stage E host: exact signed root receipt, before-image and audit gates.

These tests run only in disposable local paths. No systemctl or production
provider is invoked and no synthetic proof is accepted in production mode.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_e_native_root_host as native
from tools import pmv4_e_native_systemd_adapter as unit
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_replacement_unit_bundle as bundle
from tools.tests.test_pmv4_e_signed_native_ledger import (
    CANDIDATE, ROLLBACK, KEY, approval,
)


class FakeOriginalNativeHost:
    def __init__(self):
        self.host_count=0
        self.freeze_count=0
        self.snapshot={name:{"running":True,"revision":ROLLBACK}
                       for name in native.PROTECTED}
    @contextmanager
    def host_transaction(self):
        self.host_count+=1
        try: yield
        finally: self.host_count-=1
    @contextmanager
    def freeze_transaction(self,expected):
        assert len(expected)==64
        assert self.host_count==1
        self.freeze_count+=1
        try: yield
        finally:self.freeze_count-=1
    def protected(self):
        return self.snapshot


class FakeCode:
    def __init__(self,path):
        self.targets={native.code.POLICY:path}
        self.prior_sha256={native.code.POLICY:packet.EXPECTED_PRIOR_ROOT_POLICY}
        self.prepare_count=0
    def prepare(self,*,candidate,scope):
        self.prepare_count+=1
        assert candidate==CANDIDATE and scope["candidate_sha"]==candidate
        return {"status":"signed_native_code_before_image_ready"}
    def verify(self,*,candidate,scope):
        assert candidate==CANDIDATE
        return {"status":"native_reviewed_controlplane_bytes_installed",
                "files":len(native.code.OBJECTS)}
    def restore(self,*,candidate,scope):
        assert candidate==CANDIDATE
        return {"status":"native_original_controlplane_bytes_restored"}


class FakeSurface:
    def __init__(self):
        self.replacements_active=True
    def verify_final(self,*,replacement):
        return self.replacements_active if replacement else not self.replacements_active


def setup_host(tmp_path):
    root=contract.draft(candidate_sha=CANDIDATE,rollback_sha=ROLLBACK)
    manifest,scope=root["manifest"],root["source_scope"]
    signed=approval(manifest)
    approval_id=signed["payload"]["approval_id"]
    receipts=tmp_path/"receipts"
    receipts.mkdir(mode=0o700)
    before_dir=tmp_path/"physical-before";before_dir.mkdir(mode=0o700)
    step_dir=tmp_path/"steps";step_dir.mkdir(mode=0o700)
    freeze=tmp_path/"freeze"
    freeze.write_bytes(b"protected freeze example")
    freeze.chmod(0o600)
    policy=tmp_path/"protected-root-policy.json"
    policy.write_bytes((packet.ROOT/native.code.POLICY).read_bytes())
    policy.chmod(0o600)
    first="2026-11-19T14:01:01+00:00"
    second="2026-11-19T14:02:02+00:00"
    scans=iter((first,second,second))
    old=unit.Before(
        active=frozenset(unit.OLD),enabled=frozenset(unit.OLD),
        policy_sha256=packet.EXPECTED_PRIOR_ROOT_POLICY,
        source_sha=ROLLBACK,
        freeze_sha256=sha256(freeze.read_bytes()).hexdigest(),
        protected_fingerprint=native.digest(native.canonical(
            FakeOriginalNativeHost().snapshot)),
        claims_fingerprint="1"*64,
        marker_present=False,
    )
    core=FakeOriginalNativeHost()
    code=FakeCode(policy)
    sys=FakeSurface()
    host=native.NativeStageEHost(
        manifest=manifest,scope=scope,owner_proof=signed,
        receipt_dir=receipts,before_dir=before_dir,step_dir=step_dir,
        marker=tmp_path/"accepted.json",
        current=tmp_path/"current",
        freeze=freeze,
        source_root=packet.ROOT,
        test_owner_public_key=KEY.public_key(),
        test_before_evidence=lambda:old,
        owner_evidence=lambda:{
            "status":"live_external_ticket_core_exclusive_owner_verified",
            "unique_owner":True,"exclusive_owner_count":1,
            "production_mutations":False,
        },
        scan_evidence=lambda:{
            "status":"fresh","duplicate_items":0,
            "observed_at":next(scans, second),
        },
        core_host=core,code_switch=code,systemd=sys,production=False)
    row={
        "schema_version":"1.0","state":"started",
        "component_id":contract.COMPONENT,"approval_id":approval_id,
        "candidate_sha":CANDIDATE,"rollback_sha":ROLLBACK,
        "scope_sha256":manifest["source_scope_sha256"],
        "manifest_sha256":native.digest(native.canonical(manifest)),
        "freeze_sha256":manifest["freeze_sha256"],
        "signed_owner_proof":signed,
        "started_at":datetime.now(timezone.utc).isoformat(),
    }
    receipt=receipts/("owner-"+approval_id+".json")
    receipt.write_text(json.dumps(row))
    receipt.chmod(0o600)
    return host,old,row,receipt,core,code,sys


def test_native_host_rejects_source_checkout_as_production_root(tmp_path):
    h,old,row,receipt,core,code,sys=setup_host(tmp_path)
    with pytest.raises(native.StageEHostDenied,match="ROOT_INSTALLED_ENTRY_REQUIRED"):
        native.NativeStageEHost(
            manifest=h.manifest,scope=h.scope,owner_proof=h.owner_proof,
            production=True,core_host=core,systemd=sys,code_switch=code)


def test_signed_native_receipt_requires_original_shared_host_and_freeze_locks(tmp_path):
    host,old,row,receipt,core,code,sys=setup_host(tmp_path)
    with pytest.raises(native.StageEHostDenied,match="HOST_AND_FREEZE_LOCK_REQUIRED"):
        host.native_started_receipt_verified(CANDIDATE,ROLLBACK,
                                           host.manifest["source_scope_sha256"])
    with host.host_transaction():
        with host.freeze_transaction(host.manifest["freeze_sha256"]):
            assert host.native_started_receipt_verified(
                CANDIDATE,ROLLBACK,host.manifest["source_scope_sha256"])
            with pytest.raises(native.StageEHostDenied,match="CALL_ARGUMENT_CHANGED"):
                host.native_started_receipt_verified(
                    "f"*40,ROLLBACK,host.manifest["source_scope_sha256"])
    assert core.host_count==core.freeze_count==0


def test_one_exact_durable_physical_before_image_then_audited_steps(tmp_path):
    host,old,row,receipt,core,code,sys=setup_host(tmp_path)
    with host.host_transaction(),host.freeze_transaction(host.manifest["freeze_sha256"]):
        assert host.read_protected_before()==old
        assert host.trusted_exact_plan(CANDIDATE,ROLLBACK,
                host.manifest["source_scope_sha256"],old)
        host.persist_root_before_image(old)
        assert code.prepare_count==1
        assert host._physical_before()==old
        host.append_native_step_receipt("check_exact_baseline",old)
        host.append_native_step_receipt("checkpoint_durable_claims",old)
        audit=host.step_dir/(CANDIDATE+".jsonl")
        events=[json.loads(v) for v in audit.read_text().splitlines()]
        assert len(events)==2
        assert events[0]["previous_sha256"]=="0"*64
        assert events[1]["previous_sha256"]==events[0]["entry_sha256"]
        with pytest.raises(native.StageEHostDenied,match="PHYSICAL_BEFORE_IMAGE_REPLAY"):
            host.persist_root_before_image(old)


def test_audit_fails_closed_on_tampered_prior_chain(tmp_path):
    host,old,row,receipt,core,code,sys=setup_host(tmp_path)
    with host.host_transaction(),host.freeze_transaction(host.manifest["freeze_sha256"]):
        host.read_protected_before()
        host.persist_root_before_image(old)
        host.append_native_step_receipt("check_exact_baseline",old)
        path=host.step_dir/(CANDIDATE+".jsonl")
        entry=json.loads(path.read_text().strip())
        entry["previous_sha256"]="f"*64
        path.write_text(json.dumps(entry)+"\n")
        with pytest.raises(native.StageEHostDenied,match="STEP_AUDIT_CHAIN_DRIFT"):
            host.append_native_step_receipt("checkpoint_durable_claims",old)


def test_forged_native_started_or_signed_approval_denied(tmp_path):
    host,old,row,receipt,core,code,sys=setup_host(tmp_path)
    with host.host_transaction(),host.freeze_transaction(host.manifest["freeze_sha256"]):
        assert host.native_started_receipt_verified(
            CANDIDATE,ROLLBACK,host.manifest["source_scope_sha256"])
        forged=dict(row)
        forged["approval_id"]="owner-mcp-"+"a"*32
        receipt.write_text(json.dumps(forged))
        with pytest.raises(native.StageEHostDenied,match="NATIVE_STARTED_RECEIPT_NOT_BOUND"):
            host.native_started_receipt_verified(
                CANDIDATE,ROLLBACK,host.manifest["source_scope_sha256"])


def test_marker_cannot_be_accepted_until_verified_parity_and_before_image(tmp_path):
    host,old,row,receipt,core,code,sys=setup_host(tmp_path)
    with host.host_transaction(),host.freeze_transaction(host.manifest["freeze_sha256"]):
        host.read_protected_before()
        host.persist_root_before_image(old)
        with pytest.raises(native.StageEHostDenied,match="PARITY_NOT_ACCEPTED_BEFORE_MARKER"):
            host.commit_reviewed_root_marker(
                CANDIDATE,ROLLBACK,host.manifest["source_scope_sha256"])
        assert not host.marker.exists()


def test_twelve_unit_hashes_derived_from_reviewed_source_only(tmp_path):
    host,old,row,receipt,core,code,sys=setup_host(tmp_path)
    with host.host_transaction(),host.freeze_transaction(host.manifest["freeze_sha256"]):
        hashes=host.reviewed_twelve_unit_hashes()
        source=bundle.generate(base=packet.ROOT)
        assert len(hashes)==12
        assert hashes=={p:native.digest(raw) for p,raw in source.items()}
        assert set(hashes).issubset(host.scope["exact_replacement_files_sha256"])
        bad=next(iter(source))
        host.scope["exact_replacement_files_sha256"][bad]="f"*64
        with pytest.raises(native.StageEHostDenied,match="SIGNED_REVIEWED_UNIT_SOURCE_CHANGED"):
            host.reviewed_twelve_unit_hashes()


def test_native_host_has_no_arbitrary_deploy_cli_or_issuer_and_reuses_native_locks():
    source=Path(native.__file__).read_text()
    for banned in ("subprocess.Popen(", "docker restart ", "systemctl start ",
                   "sudo /usr/bin", "issue_exact_owner_release(", "os.system("):
        assert banned not in source
    assert "with self.core_host.host_transaction()" in source
    assert "with self.core_host.freeze_transaction(expected)" in source
