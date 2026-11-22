"""Immutable source-only no-provider generic controller canary candidate."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tools import pmv4_e_canary_packet as packet
from tools import pmv4_e_canary_contract as contract
from tools import independent_component_release as native

BASE=Path(__file__).resolve().parents[2]


def repo_fixture(tmp_path):
    repo=tmp_path/"repo"
    repo.mkdir()
    for rel in packet.REVIEWED_FILES:
        p=repo/rel
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes((BASE/rel).read_bytes())
    def git(*args):
        return subprocess.check_output(["git","-C",str(repo),*args],
                                       text=True,timeout=10).strip()
    git("init","-q")
    git("config","user.name","Source Only")
    git("config","user.email","source-only@example.invalid")
    git("add",".")
    git("commit","-qm","exact source")
    sha=git("rev-parse","HEAD")
    return repo,sha


def reviewed_image():
    return {
        "image_sha256":contract.IMAGE,
        "image_source_sha":contract.IMAGE_SOURCE,
        "component_label":"pmv4-shadow",
        "provider_mutations_disabled":True,
        "production_core_excluded":True,
    }


def source_packet(tmp_path,**kw):
    repo,sha=repo_fixture(tmp_path)
    dest=tmp_path/"prepared"
    report=packet.prepare(
        sha=sha,repo=repo,dest=dest,
        protected_main=kw.pop("protected_main",lambda repo,sha:True),
        verified_ci=kw.pop("verified_ci",lambda sha:True),
        verified_image=kw.pop("verified_image",reviewed_image),
        **kw)
    return repo,sha,dest,report


def test_source_packet_exact_git_commit_image_origin_and_zero_rollback(tmp_path):
    repo,sha,dest,report=source_packet(tmp_path)
    assert report["status"]=="preproduction_not_authorized"
    assert report["candidate_sha"]==sha
    assert report["rollback_sha"]=="0"*40
    assert report["image_source_revision"]==contract.IMAGE_SOURCE
    assert report["image_digest"]==contract.IMAGE
    assert report["owner_proof_issued"] is False
    assert report["root_installed"] is False
    assert report["production_mutations"] is False
    assert report["provider_calls"]==0
    assert report["financial_controller_modified"] is False
    m=json.loads((dest/"manifest.json").read_bytes())
    scope=json.loads((dest/"scope.json").read_bytes())
    native.validate_manifest(m)
    native.validate_scope(m,scope)
    native.validate_compose((dest/"compose.yaml").read_bytes(),m)
    assert m["candidate_sha"]==sha
    assert m["rollback_sha"]=="0"*40
    assert m["provider_scope"]==contract.SCOPE
    assert report["manifest_sha256"]==sha256(native.canonical(m)).hexdigest()
    assert report["scope_sha256"]==m["scope_sha256"]
    assert {p.name for p in dest.iterdir()}=={
        "manifest.json","scope.json","compose.yaml",
        "config.json","source-evidence.json"}
    assert all(p.stat().st_mode&0o777==0o400 for p in dest.iterdir())


def test_worktree_edits_do_not_mutate_pinned_git_source_packet(tmp_path):
    repo,sha=repo_fixture(tmp_path)
    source=(repo/"infrastructure/pmv4-e-canary/compose.yaml")
    source.write_text("unsafe, not committed")
    dest=tmp_path/"packet"
    report=packet.prepare(
        sha=sha,repo=repo,dest=dest,
        protected_main=lambda *_:True,
        verified_ci=lambda _:True,verified_image=reviewed_image)
    assert (dest/"compose.yaml").read_bytes()==(BASE/"infrastructure/pmv4-e-canary/compose.yaml").read_bytes()
    assert source.read_bytes()!=(dest/"compose.yaml").read_bytes()
    assert report["production_mutations"] is False


def test_protected_source_must_be_current_main(tmp_path):
    repo,sha=repo_fixture(tmp_path)
    dest=tmp_path/"packet"
    with pytest.raises(packet.CanaryPacketDenied,match="PROTECTED_MAIN_REQUIRED"):
        packet.prepare(
            sha=sha,repo=repo,dest=dest,
            protected_main=lambda *_:False,
            verified_ci=lambda _:True,verified_image=reviewed_image)
    assert not dest.exists()


def test_current_main_never_replaces_required_ci(tmp_path):
    repo,sha=repo_fixture(tmp_path)
    dest=tmp_path/"packet"
    with pytest.raises(packet.CanaryPacketDenied,match="PROTECTED_REQUIRED_CI_NOT_GREEN"):
        packet.prepare(
            sha=sha,repo=repo,dest=dest,
            protected_main=lambda *_:True,
            verified_ci=lambda _:False,verified_image=reviewed_image)
    assert not dest.exists()


@pytest.mark.parametrize("field,bad",[
    ("image_sha256","sha256:"+"f"*64),
    ("image_source_sha","a"*40),
    ("provider_mutations_disabled",False),
    ("production_core_excluded",False),
])
def test_untrusted_reused_image_cannot_be_staged(tmp_path,field,bad):
    repo,sha=repo_fixture(tmp_path)
    image=reviewed_image();image[field]=bad
    dest=tmp_path/"packet"
    with pytest.raises(packet.CanaryPacketDenied,match="IMAGE_SOURCE_BOUNDARY_NOT_EXACT"):
        packet.prepare(
            sha=sha,repo=repo,dest=dest,
            protected_main=lambda *_:True,
            verified_ci=lambda _:True,
            verified_image=lambda:image)
    assert not dest.exists()


def test_same_source_packet_cannot_be_overwritten(tmp_path):
    repo,sha,dest,report=source_packet(tmp_path)
    old={p.name:p.read_bytes() for p in dest.iterdir()}
    with pytest.raises(packet.CanaryPacketDenied,match="EXACT_SOURCE_ALREADY_STAGED"):
        packet.prepare(
            sha=sha,repo=repo,dest=dest,
            protected_main=lambda *_:True,
            verified_ci=lambda _:True,verified_image=reviewed_image)
    assert old=={p.name:p.read_bytes() for p in dest.iterdir()}


@pytest.mark.parametrize("other",[
    "/var/lib/jason/pmv4-e-canary-packet",
    "/etc/jason/pmv4-e-canary-packet",
    "/opt/jason/pmv4-e-canary-packet",
])
def test_packager_denies_production_destinations(tmp_path,other):
    repo,sha=repo_fixture(tmp_path)
    with pytest.raises(packet.CanaryPacketDenied,match="DESTINATION_ROOT_FORBIDDEN"):
        packet.prepare(
            sha=sha,repo=repo,dest=Path(other),
            protected_main=lambda *_:True,
            verified_ci=lambda _:True,verified_image=reviewed_image)


def test_source_git_blob_only_exact_allowlist(tmp_path):
    repo,sha=repo_fixture(tmp_path)
    with pytest.raises(packet.CanaryPacketDenied,match="SOURCE_FILE_UNREVIEWED"):
        packet.source_at(repo,sha,".env")
    with pytest.raises(packet.CanaryPacketDenied,match="SOURCE_FILE_UNREVIEWED"):
        packet.source_at(repo,"not-a-sha",packet.REVIEWED_FILES[0])


def test_actual_image_check_is_readonly_no_release_execution():
    s=Path(packet.__file__).read_text()
    assert '["/usr/bin/docker","image","inspect",contract.IMAGE]' in s
    for bad in ("docker run","docker compose up","systemctl disable",
                "sudo ","requests.post(","curl -X POST"):
        assert bad not in s
    assert '"production_mutations":False' in s
    assert '"owner_proof_issued":False' in s
