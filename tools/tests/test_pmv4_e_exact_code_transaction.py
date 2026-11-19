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
        target.write_bytes(("legacy-exact-before:"+name).encode("utf-8"))
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
