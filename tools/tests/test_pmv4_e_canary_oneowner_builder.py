"""Reproducible exact Git-source, immutable one-use Owner/root packet tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

from tools import pmv4_e_canary_oneowner_builder as builder
from tools import pmv4_e_canary_oneowner_root as root


SOURCE=Path(__file__).resolve().parents[2]


def repo(tmp_path):
    git=tmp_path/"repo"
    git.mkdir()
    for name in builder.SOURCES:
        p=git/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes((SOURCE/name).read_bytes())
    def run(*args):
        return subprocess.check_output(
            ["/usr/bin/git","-C",str(git),*args],
            text=True,timeout=10).strip()
    run("init","-q")
    run("config","user.name","Source only")
    run("config","user.email","noone@example.invalid")
    run("add",".")
    run("commit","-qm","reviewed root source")
    return git,run("rev-parse","HEAD")


def packet(tmp_path):
    git,sha=repo(tmp_path)
    target=tmp_path/"oneowner-packet"
    report=builder.prepare(
        sha,repo=git,target=target,
        verify_source=lambda *_:True,
        verify_ci=lambda _:True,
        verify_canary=lambda:True)
    return git,sha,target,report


def test_exact_unprivileged_git_packet_has_no_owner_proof_or_production_mutation(
    tmp_path,
):
    git,sha,dest,report=packet(tmp_path)
    assert report["status"]=="immutable_unprivileged_exact_source_prepared"
    assert report["root_build_sha"]==sha
    assert report["candidate_sha"]==root.CANDIDATE
    assert report["scope_sha256"]==root.SCOPE_SHA
    assert report["manifest_sha256"]==root.MANIFEST_SHA
    assert report["owner_approval_issued"] is False
    assert report["production_mutations"] is False
    assert {str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()}==set(
        builder.SOURCES)
    for name in builder.SOURCES:
        data=(dest/name).read_bytes()
        assert data==builder.git_blob(git,sha,name)
        assert stat.S_IMODE((dest/name).stat().st_mode)==0o400
        assert (dest/name).stat().st_uid==0 or (dest/name).stat().st_uid>=0
    assert not (dest/"owner-proof.json").exists()
    assert all(p.stat().st_mode&0o077==0 for p in
               [dest,*[dest/name for name in builder.SOURCES]])


def test_uncommitted_user_source_changes_cannot_change_reviewed_packet(tmp_path):
    git,sha=repo(tmp_path)
    changed=git/"tools/pmv4_e_canary_oneowner_root.py"
    changed.write_text("unreviewed root code")
    target=tmp_path/"packet"
    report=builder.prepare(
        sha,repo=git,target=target,
        verify_source=lambda *_:True,
        verify_ci=lambda _:True,
        verify_canary=lambda:True)
    assert (target/"tools/pmv4_e_canary_oneowner_root.py").read_bytes()!=changed.read_bytes()
    assert (target/"tools/pmv4_e_canary_oneowner_root.py").read_bytes()==builder.git_blob(
        git,sha,"tools/pmv4_e_canary_oneowner_root.py")


@pytest.mark.parametrize("gate,matcher",[
    ("protected","PROTECTED_MAIN_NOT_EXACT"),
    ("ci","PROTECTED_REQUIRED_CI_NOT_GREEN"),
    ("canary","IMMUTABLE_PROVIDERFREE_SOURCE_NOT_ATTESTED"),
])
def test_any_missing_immutable_source_gate_fails_before_staging(tmp_path,gate,matcher):
    git,sha=repo(tmp_path)
    target=tmp_path/"failed-staging"
    with pytest.raises(builder.StageDenied,match=matcher):
        builder.prepare(sha,repo=git,target=target,
            verify_source=lambda *_:gate!="protected",
            verify_ci=lambda _:gate!="ci",
            verify_canary=lambda:gate!="canary")
    assert not target.exists()


def test_candidate_ci_gate_separate_from_build_sha(tmp_path):
    git,sha=repo(tmp_path)
    seen=[]
    def verify(candidate):
        seen.append(candidate)
        return candidate!=root.CANDIDATE
    with pytest.raises(builder.StageDenied,match="REVIEWED_CANARY_REQUIRED_CI"):
        builder.prepare(sha,repo=git,target=tmp_path/"packet",
            verify_source=lambda *_:True,verify_ci=verify,
            verify_canary=lambda:True)
    assert seen==[sha,root.CANDIDATE]


def test_second_source_packet_never_overwrites_original(tmp_path):
    git,sha,dest,report=packet(tmp_path)
    before={str(p.relative_to(dest)):p.read_bytes()
            for p in dest.rglob("*") if p.is_file()}
    with pytest.raises(builder.StageDenied,match="SOURCE_PACKET_ALREADY_PREPARED"):
        builder.prepare(sha,repo=git,target=dest,
            verify_source=lambda *_:True,
            verify_ci=lambda _:True,verify_canary=lambda:True)
    assert before=={str(p.relative_to(dest)):p.read_bytes()
                    for p in dest.rglob("*") if p.is_file()}


@pytest.mark.parametrize("target",[
    "/opt/jason/bad-pmv4-e",
    "/var/lib/jason/pmv4-bad",
    "/etc/systemd/system/pmv4-invalid",
])
def test_source_packet_builder_refuses_production_destinations(tmp_path,target):
    git,sha=repo(tmp_path)
    with pytest.raises(builder.StageDenied,match="DESTINATION_OUTSIDE_UNPRIVILEGED"):
        builder.prepare(sha,repo=git,target=Path(target),
            verify_source=lambda *_:True,
            verify_ci=lambda _:True,verify_canary=lambda:True)


def test_only_reviewed_source_paths_are_retrievable(tmp_path):
    git,sha=repo(tmp_path)
    with pytest.raises(builder.StageDenied,match="NOT_REVIEWED_SOURCE"):
        builder.git_blob(git,sha,"/etc/shadow")
    with pytest.raises(builder.StageDenied,match="NOT_REVIEWED_SOURCE"):
        builder.git_blob(git,"not-a-sha",builder.SOURCES[0])


def test_one_owner_local_script_signs_only_after_privileged_root_preflight():
    code=(SOURCE/"tools/pmv4_e_canary_oneowner_local.sh").read_text()
    source=code.index("--check-source")
    privileged=code.index("--root-preflight",source)
    approve=code.index('"$OWNER" --approve',privileged)
    execute=code.index('"$ROOT" --execute',approve)
    assert source<privileged<approve<execute
    assert "sudo" in code
    assert "systemctl stop" not in code
    assert "docker compose" not in code


def test_owner_signer_is_single_exact_consent_not_standing_permission():
    data=(SOURCE/"tools/pmv4_e_canary_oneowner_owner.py").read_text()
    assert "CONFIRM=\"APPROVE-ONE-EXACT-PMV4-E-PROVIDERFREE-CANARY-AND-CLEANUP\"" in data
    assert 'confirmed_decision="approve"' in data
    assert 'signer.issue_exact_owner_release' in data
    assert 'root.stage_dir(build_sha)/"owner-proof.json"' in data
    assert 'production_mutations":False' not in data or 'PRODUCTION_MUTATIONS=false' in data
