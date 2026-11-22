"""Signed original locks and exact reviewed source hash closure, no live host."""
from hashlib import sha256
from pathlib import Path
import json
import stat

import pytest

from tools import pmv4_e_immutable_source_stage as stage
from tools import pmv4_e_exact_release_packet as packet
from tools import pmv4_e_root_trust_stage as roottrust


def instance(tmp_path):
    target=tmp_path/"releases";target.mkdir(mode=0o700)
    facts={"owner":True,"host":True,"freeze":True,"marker":True,"inert":True}
    s=stage.ImmutableRootSourceStage(
        source=packet.ROOT,target_parent=target,
        exact_owner_verified=lambda:facts["owner"],
        original_host_locked=lambda:facts["host"],
        original_freeze_locked=lambda:facts["freeze"],
        marker_absent=lambda:facts["marker"],
        replacement_inert=lambda:facts["inert"],
        production=False)
    hashes={name:sha256((packet.ROOT/name).read_bytes()).hexdigest()
            for name in packet.REVIEWED_PATHS}
    return s,facts,hashes


def test_full_exact_immutable_staging_then_existing_trust_stager(tmp_path):
    s,facts,hashes=instance(tmp_path)
    sha="b"*40
    out=s.stage(candidate=sha,exact_hashes=hashes)
    assert out["status"]=="exact_immutable_candidate_source_staged_inert"
    assert out["production_unit_changes"] is False
    source=s.target_parent/sha
    assert len(list(source.rglob("*")))>len(hashes)
    assert all(stat.S_IMODE((source/p).lstat().st_mode)==0o444
               for p in hashes)
    assert s.verify(candidate=sha,exact_hashes=hashes)["source_file_count"]==len(hashes)
    result=roottrust.RootTrustStager(
        source=source,target=tmp_path/"stage-e-trusted",
        native_signed_started=lambda:True,
        native_host_locked=lambda:facts["host"],
        native_freeze_locked=lambda:facts["freeze"],
        native_marker_absent=lambda:facts["marker"],
        native_replacements_inert=lambda:facts["inert"],
        production=False).stage(source_sha=sha,exact_hashes=hashes)
    assert result["installed_file_count"]==len(hashes)
    assert s.recover_inert(candidate=sha,exact_hashes=hashes)["removed_files"]==len(hashes)
    assert not source.exists()


@pytest.mark.parametrize("missing",[
    "owner","host","freeze","marker","inert",
])
def test_missing_exact_owner_or_original_native_locks_never_stages(
        tmp_path,missing):
    s,facts,hashes=instance(tmp_path)
    facts[missing]=False
    with pytest.raises(stage.RootSourceStageDenied):
        s.stage(candidate="b"*40,exact_hashes=hashes)
    assert list(s.target_parent.iterdir())==[]


def test_wrong_manifest_hash_and_extra_file_denied_before_root_write(tmp_path):
    s,facts,hashes=instance(tmp_path)
    key=next(iter(hashes))
    altered=dict(hashes);altered[key]="0"*64
    with pytest.raises(stage.RootSourceStageDenied):
        s.stage(candidate="b"*40,exact_hashes=altered)
    assert list(s.target_parent.iterdir())==[]
    altered=dict(hashes);altered["unreviewed/agent.py"]="f"*64
    with pytest.raises(stage.RootSourceStageDenied,
                       match="EXACT_REVIEWED_FILE_INVENTORY_REQUIRED"):
        s.stage(candidate="b"*40,exact_hashes=altered)


def test_modified_installed_file_blocks_recovery_without_deleting(tmp_path):
    s,facts,hashes=instance(tmp_path)
    s.stage(candidate="b"*40,exact_hashes=hashes)
    victim=s.target_parent/("b"*40)/next(iter(hashes))
    victim.chmod(0o644)
    victim.write_text("foreign code")
    victim.chmod(0o444)
    with pytest.raises(stage.RootSourceStageDenied,
                       match="RELEASE_INSTALLED_FILE_DIGEST_CHANGED"):
        s.recover_inert(candidate="b"*40,exact_hashes=hashes)
    assert victim.read_text()=="foreign code"


def test_second_install_denied_one_exact_candidate_only(tmp_path):
    s,facts,hashes=instance(tmp_path)
    s.stage(candidate="b"*40,exact_hashes=hashes)
    with pytest.raises(stage.RootSourceStageDenied,
                       match="RELEASE_ALREADY_STAGED_OR_INTERRUPTED"):
        s.stage(candidate="b"*40,exact_hashes=hashes)


def test_source_only_cannot_self_bootstrap_as_production_root(tmp_path):
    with pytest.raises(stage.RootSourceStageDenied,
                       match="CANONICAL_SIGNED_ROOT_INSTALL_REQUIRED"):
        stage.ImmutableRootSourceStage(
            source=packet.ROOT,target_parent=tmp_path,
            exact_owner_verified=lambda:True,
            original_host_locked=lambda:True,
            original_freeze_locked=lambda:True,
            marker_absent=lambda:True,
            replacement_inert=lambda:True,
            production=True)
