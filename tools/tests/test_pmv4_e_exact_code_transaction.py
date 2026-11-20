"""Exact durable before-image and bounded code/policy swap under native locks."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import os
import stat

import pytest

from tools import pmv4_e_exact_code_transaction as code
from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_root_trust_stage as trust


def sample(tmp_path):
    sealed=tmp_path/"sealed-root"
    hashes={
        rel:sha256((packet.ROOT/rel).read_bytes()).hexdigest()
        for rel in packet.REVIEWED_PATHS
    }
    trust.RootTrustStager(
        source=packet.ROOT,target=sealed,production=False,
        native_signed_started=lambda:True,
        native_host_locked=lambda:True,
        native_freeze_locked=lambda:True,
        native_marker_absent=lambda:True,
        native_replacements_inert=lambda:True,
    ).stage(source_sha="b"*40,exact_hashes=hashes)
    source=sealed
    oldroot=tmp_path/"current"
    oldroot.mkdir()
    snapshot=tmp_path/"before";snapshot.mkdir(mode=0o700)
    targets={}
    identities={}
    oldhashes={}
    for name in code.OBJECTS:
        target=oldroot/Path(name).name
        # A production file has verified old SHA, but test needs a synthetic
        # independently sealed old baseline. Caller cannot substitute hashes
        # in production mode.
        target.write_bytes(
            (source/code.POLICY).read_bytes() if name==code.POLICY
            else ("legacy-exact-before:"+name).encode("utf-8"))
        target.chmod(0o600)
        targets[name]=target
        oldhashes[name]=sha256(target.read_bytes()).hexdigest()
        identities[name]=(os.getuid(),os.getgid(),0o600)
    state={"start":True,"host":True,"freeze":True,"no_marker":True}
    c=code.StageECodeTransaction(
        source_root=source,before_root=snapshot,
        targets=targets,identities=identities,
        prior_sha256=oldhashes,
        signed_started=lambda:state["start"],
        shared_host_lock=lambda:state["host"],
        freeze_lock=lambda:state["freeze"],
        replacement_marker_absent=lambda:state["no_marker"],
        production=False)
    source_scope=contract.draft(
        candidate_sha="b"*40,rollback_sha="a"*40)["source_scope"]
    return c,state,targets,source_scope


def test_native_durable_before_image_atomic_install_and_rollback(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    old={k:v.read_bytes() for k,v in targets.items()}
    first=c.prepare(candidate="b"*40,scope=scope)
    assert first["status"]=="signed_native_code_before_image_ready"
    assert first["code_mutations"] is False
    assert old=={k:v.read_bytes() for k,v in targets.items()}
    applied=c.apply(candidate="b"*40,scope=scope)
    assert applied["status"]=="native_reviewed_controlplane_bytes_installed"
    assert applied["service_restarts"]==0
    assert c.verify(candidate="b"*40,scope=scope)==applied
    restored=c.restore(candidate="b"*40,scope=scope)
    assert restored["status"]=="native_original_controlplane_bytes_restored"
    assert old=={k:v.read_bytes() for k,v in targets.items()}
    assert c.restore(candidate="b"*40,scope=scope)==restored


def test_missing_signed_started_host_or_freeze_lock_denies_before_file_write(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    original={k:v.read_bytes() for k,v in targets.items()}
    for k in state:
        state[k]=False
        with pytest.raises(code.StageECodeTransactionDenied):
            c.prepare(candidate="b"*40,scope=scope)
        assert not list(c.before_root.iterdir())
        assert original=={name:p.read_bytes() for name,p in targets.items()}
        state[k]=True


def test_denies_unknown_code_targets_and_nonroot_production(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    with pytest.raises(code.StageECodeTransactionDenied,
                       match="FILE_SCOPE_NOT_EXACT"):
        code.StageECodeTransaction(
            source_root=packet.ROOT,before_root=c.before_root,
            targets={**targets,"tools/unreviewed.py":tmp_path/"unknown.py"},
            identities=c.identities,prior_sha256=c.prior_sha256,
            signed_started=lambda:True,
            shared_host_lock=lambda:True,freeze_lock=lambda:True,
            replacement_marker_absent=lambda:True,
            production=False)
    with pytest.raises(code.StageECodeTransactionDenied,
                       match="PRODUCTION_ROOT_SOURCE_NOT_IMMUTABLE"):
        code.StageECodeTransaction(
            signed_started=lambda:True,shared_host_lock=lambda:True,
            freeze_lock=lambda:True,replacement_marker_absent=lambda:True,
            production=True)


def test_exact_immutable_before_image_cannot_be_replayed(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    c.prepare(candidate="b"*40,scope=scope)
    with pytest.raises(code.StageECodeTransactionDenied,
                       match="BEFORE_IMAGE_ALREADY_EXISTS"):
        c.prepare(candidate="b"*40,scope=scope)


def test_partial_candidate_file_failure_is_rollback_safe(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    baseline={k:v.read_bytes() for k,v in targets.items()}
    c.prepare(candidate="b"*40,scope=scope)
    candidate=c._reviewed_candidate(scope)
    name=sorted(code.OBJECTS)[0]
    path=targets[name]
    path.write_bytes(candidate[name])
    c.restore(candidate="b"*40,scope=scope)
    assert baseline=={k:v.read_bytes() for k,v in targets.items()}


def test_foreign_file_change_denies_recovery_without_overwriting(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    c.prepare(candidate="b"*40,scope=scope)
    path=targets[code.WATCHDOG]
    path.write_bytes(b"foreign code")
    with pytest.raises(code.StageECodeTransactionDenied,
                       match="ROLLBACK_UNKNOWN_INSTALLED_FILE"):
        c.restore(candidate="b"*40,scope=scope)
    assert path.read_bytes()==b"foreign code"


def test_bad_signed_scope_or_missing_reviewed_source_denied(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    wrong=dict(scope)
    wrong["source_candidate_policy_sha256"]="f"*64
    with pytest.raises(code.StageECodeTransactionDenied):
        c.prepare(candidate="b"*40,scope=wrong)
    wrong=dict(scope)
    wrong["action"]="unreviewed"
    with pytest.raises(code.StageECodeTransactionDenied):
        c.prepare(candidate="b"*40,scope=wrong)


def test_snapshot_not_accidentally_production_authority(tmp_path):
    c,state,targets,scope=sample(tmp_path)
    c.prepare(candidate="b"*40,scope=scope)
    p=c.before_root/("b"*40)/"manifest.json"
    record=json.loads(p.read_text())
    assert record["code_mutations"] is False
    assert not record.get("owner_approval_issued",False)
    assert not record.get("native_release_accepted",False)


def test_protected_root_policy_approvals_preserved_not_replaced_from_source(
        tmp_path):
    c,state,targets,scope=sample(tmp_path)
    p=targets[code.POLICY]
    original=json.loads(p.read_bytes())
    # A protected policy can include separate historical monitoring and
    # container allowances absent from the public source copy.
    allowed=list(original.get("allowed_running_containers") or [])
    allowed.append("aot-root-only-existing-protected-monitor")
    original["allowed_running_containers"]=sorted(set(allowed))
    raw=code.parity.canon(original)
    p.write_bytes(raw)
    c.prior_sha256[code.POLICY]=code.digest(raw)
    c.prepare(candidate="b"*40,scope=scope)
    c.apply(candidate="b"*40,scope=scope)
    new=json.loads(p.read_bytes())
    assert new["allowed_running_containers"]==original["allowed_running_containers"]
    assert new["schema_version"]==original["schema_version"]
    assert new["required_system_units"]!=original["required_system_units"]
    assert new["required_user_units"]!=original["required_user_units"]
    c.restore(candidate="b"*40,scope=scope)
    assert p.read_bytes()==raw


def test_root_only_legacy_unit_mismatch_rejected_before_writing_snapshot(
        tmp_path):
    c,state,targets,scope=sample(tmp_path)
    p=targets[code.POLICY]
    original=json.loads(p.read_bytes())
    original["required_system_units"]=[
        x for x in original["required_system_units"]
        if x!="jason-release-host-reconcile.path"
    ]
    raw=code.parity.canon(original)
    p.write_bytes(raw)
    c.prior_sha256[code.POLICY]=code.digest(raw)
    with pytest.raises((code.StageECodeTransactionDenied,
                        code.parity.PMv4SchedulingDenied)):
        c.prepare(candidate="b"*40,scope=scope)
    assert list(c.before_root.iterdir())==[]


def test_catalog_shared_worker_is_outside_native_mutation_targets():
    assert code.RECONCILER not in code.OBJECTS
    assert Path("/usr/local/lib/jason/release_host_reconcile_worker.py") not in code.DEFAULT_TARGETS.values()
    assert code.FILES == (code.WATCHDOG, code.MANAGER)


def test_exact_live_policy_baseline_preserves_scoped_backport_controls(tmp_path):
    from tools import pmv4_e_root_receipt_readback as rootproof
    from tools import pmv4_e_unit_admission as admission
    from tools import pmv4_e_canary_acceptance_readback as canary

    raw=(Path(__file__).parent/"fixtures/pmv4_e_root_policy_after_scoped_backport.json").read_bytes()
    expected="a4358f564c7b5c6ede6ccfa32d884760a247a2d5672440dbc80d771893868608"
    historical="4c9db0f4bbd12e1892b480a759d2d89b9749b84187eb2a753a260ecf326b7953"
    assert code.digest(raw)==packet.EXPECTED_PRIOR_ROOT_POLICY==expected
    assert rootproof.ACTIVE_POLICY_SHA==admission.PRIOR_POLICY==canary.LIVE_POLICY==expected
    assert canary.POLICY==historical
    original=json.loads(raw)
    preserved={
        "jason-scoped-backport-recovery.service",
        "jason-scoped-backport-recovery.timer",
        "jason-scoped-backport-requests.path",
        "jason-scoped-backport-requests.service",
    }
    old=json.loads(raw)
    old["allowed_system_units"]=[u for u in old["allowed_system_units"] if u not in preserved]
    assert code.digest((json.dumps(old,indent=2,sort_keys=True)+"\n").encode())==historical

    c,state,targets,scope=sample(tmp_path)
    p=targets[code.POLICY]
    p.write_bytes(raw)
    c.prior_sha256[code.POLICY]=expected
    c.prepare(candidate="b"*40,scope=scope)
    c.apply(candidate="b"*40,scope=scope)
    accepted=json.loads(p.read_bytes())
    assert preserved.issubset(accepted["allowed_system_units"])
    assert accepted==code.parity.plan_exact_unit_delta(original)["candidate_policy"]
    c.restore(candidate="b"*40,scope=scope)
    assert p.read_bytes()==raw
