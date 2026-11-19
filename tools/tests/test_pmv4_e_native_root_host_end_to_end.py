"""Real Stage E NativeStageEHost with signed original ledger and systemd files.

All mutations are bounded to disposable tmp_path and a simulated systemctl.
The original ledger, its exact Owner signature, before-image transaction,
new root-host callbacks, 12 generated unit bytes and rollback run together.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path

import pytest

from tools import pmv4_e_native_root_host as hostcode
from tools import pmv4_e_native_backend_bridge as bridge
from tools import pmv4_e_native_systemd_adapter as adapter
from tools import pmv4_e_signed_native_ledger as signed
from tools import pmv4_e_systemd_root_ops as ops
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_code_transaction as code
from tools.tests.test_pmv4_e_exact_code_transaction import sample as code_fixture
from tools.tests.test_pmv4_e_signed_native_ledger import (
    Host,fixture,approval,records,CANDIDATE,ROLLBACK,KEY,
)
from tools.tests.test_pmv4_e_systemd_root_ops import FakeSystemctl


class OriginalCore(Host):
    def host_transaction(self):
        return self.lock()
    def freeze_transaction(self,expected):
        return self.freeze(expected)


def integration(tmp_path):
    ledger_root,manifest=fixture(tmp_path)
    proof=approval(manifest)
    workspace=tmp_path/"stage-e-code"
    workspace.mkdir()
    code_switch,state,targets,scope=code_fixture(workspace)
    sealed=code_switch.source_root
    assert contract.validate(manifest,scope,source_root=sealed)["candidate_sha"]==CANDIDATE
    sys=FakeSystemctl()
    user_units=tmp_path/"units-user";user_units.mkdir()
    root_units=tmp_path/"units-root";root_units.mkdir()
    surface=ops.ExactSystemdSurface(
        production=False,runner=sys,user_dir=user_units,system_dir=root_units,
        trusted_dir=sealed/"infrastructure/pmv4-e-scheduler/systemd")
    receipt_dir=ledger_root/"receipts"
    before_dir=tmp_path/"physical-before";before_dir.mkdir(mode=0o700)
    step_dir=tmp_path/"audits";step_dir.mkdir(mode=0o700)
    accepted=tmp_path/"marker"/"accepted.json"
    accepted.parent.mkdir(mode=0o755)
    freeze=tmp_path/"test-freeze"
    freeze.write_bytes(b"native-test-only-unchanged-freeze")
    freeze.chmod(0o600)
    current_dir=tmp_path/"releases"/ROLLBACK
    current_dir.mkdir(parents=True)
    current=tmp_path/"current"
    current.symlink_to(current_dir,target_is_directory=True)
    core=OriginalCore()
    seen=iter((
        "2026-11-19T14:01:00+00:00",
        "2026-11-19T14:02:00+00:00",
        "2026-11-19T14:03:00+00:00",
    ))
    final="2026-11-19T14:03:00+00:00"
    before=adapter.Before(
        active=frozenset(adapter.OLD),enabled=frozenset(adapter.OLD),
        policy_sha256=hostcode.packet.EXPECTED_PRIOR_ROOT_POLICY,
        source_sha=ROLLBACK,
        freeze_sha256=sha256(freeze.read_bytes()).hexdigest(),
        protected_fingerprint=hostcode.digest(hostcode.canonical(core.protected())),
        claims_fingerprint="a"*64,marker_present=False,
    )
    host=hostcode.NativeStageEHost(
        manifest=manifest,scope=scope,owner_proof=proof,production=False,
        core_host=core,code_switch=code_switch,systemd=surface,
        receipt_dir=receipt_dir,before_dir=before_dir,step_dir=step_dir,
        marker=accepted,current=current,freeze=freeze,source_root=sealed,
        test_owner_public_key=KEY.public_key(),
        test_before_evidence=lambda:before,
        owner_evidence=lambda:{
            "status":"live_external_ticket_core_exclusive_owner_verified",
            "unique_owner":True,"exclusive_owner_count":1,
            "production_mutations":False,
        },
        scan_evidence=lambda:{
            "status":"fresh","observed_at":next(seen,final),
            "duplicate_items":0,"provider_items":142,"evaluated":142,
        },
    )
    code_switch.signed_started=lambda:host.native_started_receipt_verified(
        CANDIDATE,ROLLBACK,manifest["source_scope_sha256"])
    code_switch.shared_host_lock=lambda:host.host_locked
    code_switch.freeze_lock=lambda:host.freeze_locked
    code_switch.replacement_marker_absent=lambda:not host._marker_present()

    wrapped=bridge.StageERootBridge(native_root=host,systemd=surface)
    unit_adapter=adapter.StageEUnitAdapter(
        wrapped,native_invocation=lambda:host.host_locked and host.freeze_locked)
    installed={"sha":ROLLBACK}
    fail={"after_activate":False}
    def activate(bundle,manifest):
        unit_adapter.activate(
            candidate_sha=manifest["candidate_sha"],
            rollback_sha=manifest["rollback_sha"],
            scope_sha256=manifest["source_scope_sha256"],
            action=manifest["action"])
        installed["sha"]=CANDIDATE
    def restore(_prior,manifest):
        unit_adapter.restore(
            rollback_sha=manifest["rollback_sha"],
            scope_sha256=manifest["source_scope_sha256"])
        installed["sha"]=ROLLBACK
    def verify(bundle,manifest):
        attested=host.verify_component(bundle,manifest)
        if bundle.name==CANDIDATE and fail["after_activate"]:
            return False
        return attested
    ledger=signed.StageESignedNativeLedger(
        root=ledger_root,source_root=sealed,
        verify_stage_e_preflight=core.root_gate,
        host_transaction=host.host_transaction,
        freeze_transaction=host.freeze_transaction,
        verify_protected=core.protected,
        verify_source_and_ci=core.source,
        verify_image=lambda *_:False,
        observe_component=host.observe_component,
        activate_component=activate,
        restore_component=restore,
        verify_component=verify,
        production=False,trusted_public_key=KEY.public_key(),
    )
    ledger._freeze_bytes=lambda m:b'{"status":"active"}'
    return {
        "ledger":ledger,"host":host,"root":ledger_root,"manifest":manifest,
        "proof":proof,"sys":sys,"surface":surface,"user":user_units,
        "root_units":root_units,"code":code_switch,"before":before,
        "installed":installed,"fail":fail,"marker":accepted,
    }


def test_one_signed_original_native_controller_promotes_real_host_and_twelve_units(tmp_path):
    p=integration(tmp_path)
    result=p["ledger"].promote(p["manifest"],p["proof"])
    assert result["status"]=="native_stage_e_six_unit_accepted"
    assert p["installed"]["sha"]==CANDIDATE
    assert p["sys"].active==set(adapter.NEW)
    assert p["surface"].verify_final(replacement=True)
    assert len(list(p["user"].iterdir())+list(p["root_units"].iterdir()))==12
    assert p["marker"].exists()
    assert p["host"].parity_passed is True
    assert records(p["root"])[0]["state"]=="accepted"
    assert len((p["host"].step_dir/(CANDIDATE+".jsonl")).read_text().splitlines())==len(adapter.STEPS)
    assert p["host"].host_locked is False
    assert p["host"].freeze_locked is False


def test_complete_signed_native_failure_restores_controlplane_code_systemd_and_marker(tmp_path):
    p=integration(tmp_path)
    p["fail"]["after_activate"]=True
    with pytest.raises(PermissionError,match="LIVE_SIX_UNIT_ACCEPTANCE_FAILED"):
        p["ledger"].promote(p["manifest"],p["proof"])
    assert p["installed"]["sha"]==ROLLBACK
    assert p["sys"].active==set(adapter.OLD)
    assert p["surface"].verify_final(replacement=False)
    assert not p["marker"].exists()
    assert p["host"].parity_passed is False
    assert records(p["root"])[0]["state"]=="rolled_back"
    assert not list(p["user"].iterdir())
    assert not list(p["root_units"].iterdir())
    for rel,path in p["code"].targets.items():
        assert code.digest(path.read_bytes())==p["code"].prior_sha256[rel]
