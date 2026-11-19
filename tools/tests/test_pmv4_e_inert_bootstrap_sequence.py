"""Use original one-use owner-signed proof across inert root lifecycle."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from tools import pmv4_e_inert_bootstrap_sequence as flow
from tools import pmv4_e_immutable_source_stage as source
from tools import pmv4_e_root_trust_stage as rootstage
from tools import pmv4_e_signed_bootstrap_phase as bootstrap
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_native_release_contract as contract
from tools.tests.test_pmv4_e_signed_native_ledger import CANDIDATE,ROLLBACK,KEY,approval


def setup(tmp_path):
    d={name:tmp_path/name for name in (
        "releases","native-releases","native-receipts","bootstrap")}
    for path in d.values():path.mkdir(mode=0o700)
    controls={"owner":True,"host":True,"freeze":True,
              "old":True,"inert":True,"marker":True,"ci":True}
    checked=bootstrap.SignedInertBootstrap(
        source_root=packet.ROOT,root=d["bootstrap"],
        native_receipts=d["native-receipts"],
        host_lock_held=lambda:controls["host"],
        freeze_lock_held=lambda:controls["freeze"],
        legacy_active=lambda:controls["old"],
        replacements_inert=lambda:controls["inert"],
        marker_absent=lambda:controls["marker"],
        source_ci_verified=lambda cand:controls["ci"] and cand==CANDIDATE,
        production=False,test_owner_public_key=KEY.public_key(),
    )
    typed=contract.draft(candidate_sha=CANDIDATE,
                         rollback_sha=ROLLBACK)
    m=typed["manifest"]
    req={
        "schema_version":"1.0",
        "request_id":"release-"+CANDIDATE[:16],
        "action":bootstrap.BOOTSTRAP_ACTION,
        "candidate_sha":CANDIDATE,"rollback_sha":ROLLBACK,
        "scope_sha256":m["source_scope_sha256"],
        "manifest_sha256":typed["manifest_sha256"],
        "freeze_sha256":m["freeze_sha256"],
        "signed_owner_proof":approval(m),
    }
    root_source=source.ImmutableRootSourceStage(
        source=packet.ROOT,target_parent=d["releases"],
        exact_owner_verified=lambda:controls["owner"]
                     and controls["host"] and controls["freeze"],
        original_host_locked=lambda:controls["host"],
        original_freeze_locked=lambda:controls["freeze"],
        marker_absent=lambda:controls["marker"],
        replacement_inert=lambda:controls["inert"],
        production=False)
    stager=rootstage.RootTrustStager(
        source=d["releases"]/CANDIDATE,
        target=tmp_path/"pmv4-e-trusted",
        native_signed_started=lambda:checked.signed_started(
            candidate_sha=CANDIDATE,
            scope_sha256=m["source_scope_sha256"],
            approval_id=req["signed_owner_proof"]["payload"]["approval_id"]),
        native_host_locked=lambda:controls["host"],
        native_freeze_locked=lambda:controls["freeze"],
        native_marker_absent=lambda:controls["marker"],
        native_replacements_inert=lambda:controls["inert"],
        production=False)
    sequence=flow.InertBootstrapSequence(
        source_stager=root_source,bootstrap=checked,
        trust_stager=stager,native_releases=d["native-releases"],
        production=False)
    return sequence,req,controls,d


def test_one_authentic_owner_proof_installs_full_inert_trust_chain(tmp_path):
    flowobj,request,controls,d=setup(tmp_path)
    result=flowobj.prepare(request)
    assert result["status"]=="signed_owner_inert_stage_e_root_install_attested"
    assert result["root_authorization_to_retire"] is False
    assert result["legacy_systemd_changes"]==0
    assert result["reviewed_files"]==len(packet.REVIEWED_PATHS)
    assert result["manifest_sha256"]==request["manifest_sha256"]
    assert flowobj.trust_stager.target.is_dir()
    release=d["native-releases"]/CANDIDATE
    assert json.loads((release/"manifest.json").read_text())["candidate_sha"]==CANDIDATE
    assert json.loads((release/"source-scope.json").read_text())["rollback_sha"]==ROLLBACK
    assert len(list(release.iterdir()))==2
    assert len(list(d["bootstrap"].iterdir()))==1
    assert not list(d["native-receipts"].iterdir())
    assert controls["old"] and controls["inert"]


@pytest.mark.parametrize("flag",["owner","host","freeze","old","inert","marker","ci"])
def test_missing_guard_denies_before_any_source_staging(tmp_path,flag):
    obj,req,controls,d=setup(tmp_path)
    controls[flag]=False
    with pytest.raises(PermissionError):
        obj.prepare(req)
    assert not list(d["releases"].iterdir())
    assert not list(d["bootstrap"].iterdir())


def test_signed_bootstrap_cannot_be_reused_and_no_second_native_bundle(tmp_path):
    obj,req,controls,d=setup(tmp_path)
    obj.prepare(req)
    with pytest.raises(PermissionError):
        obj.prepare(req)
    assert len(list(d["bootstrap"].iterdir()))==1
    assert len(list(d["native-releases"].iterdir()))==1


def test_forged_owner_denied_before_root_bytes_written(tmp_path):
    obj,req,controls,d=setup(tmp_path)
    req["signed_owner_proof"]=approval(
        contract.draft(candidate_sha=CANDIDATE,
                       rollback_sha=ROLLBACK)["manifest"],
        key=Ed25519PrivateKey.generate())
    with pytest.raises(PermissionError):
        obj.prepare(req)
    assert not list(d["releases"].iterdir())
    assert not list(d["bootstrap"].iterdir())


def test_source_only_never_constructs_production_bootstrap(tmp_path):
    obj,req,controls,d=setup(tmp_path)
    with pytest.raises(flow.StageEBootstrapSequenceDenied,
                       match="CANONICAL_ROOT_BOOTSTRAP_INSTALL_REQUIRED"):
        flow.InertBootstrapSequence(
            source_stager=obj.source_stager,bootstrap=obj.bootstrap,
            trust_stager=obj.trust_stager,production=True)


def test_source_never_activates_six_triggers_or_mints_owner_proof():
    code=Path(flow.__file__).read_text()
    for s in ("systemctl start","systemctl stop","docker restart",
              "issue_exact_owner_release(", "subprocess.Popen(",
              "signed_approval = True","sudo -n"):
        assert s not in code
