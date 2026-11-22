"""Deterministic exact 60-file Stage E root-admin packet, no privileged effect."""
from hashlib import sha256
from pathlib import Path
import json
import tarfile

import pytest

from tools import pmv4_e_bootstrap_packet as b
from tools import pmv4_e_exact_release_packet as packet


def test_reviewed_root_bundle_has_exact_sha256_and_no_executable_side_effect(
        tmp_path,monkeypatch):
    monkeypatch.setattr(b,"ARTIFACTS",tmp_path)
    out=tmp_path/("pmv4-e-root-admin-bundle-"+"b"*40)
    done=b.make_packet(candidate="b"*40,rollback="a"*40,output=out)
    assert done["reviewed_file_count"]==len(packet.REVIEWED_PATHS)
    assert done["artifacts_created"]==2
    assert done["owner_approval_issued"] is False
    manifest=json.loads((out/"handoff-manifest.json").read_text())
    assert manifest["native_six_unit_promotion_authorized"] is False
    archive=out/("stage-e-trusted-"+"b"*40+".tar")
    assert sha256(archive.read_bytes()).hexdigest()==manifest["archive_sha256"]
    with tarfile.open(archive) as t:
        files={item.name:item for item in t.getmembers() if item.isfile()}
        dirs={item.name:item for item in t.getmembers() if item.isdir()}
        assert len(files)==len(packet.REVIEWED_PATHS)
        assert all(name.startswith(b.ROOT+"/") for name in files)
        assert all(item.uid==item.gid==0 and item.mode==0o444
                   and not item.issym() for item in files.values())
        assert all(item.uid==item.gid==0 and item.mode==0o555
                   for item in dirs.values())
        for rel,digest in manifest["reviewed_hashes"].items():
            assert sha256(t.extractfile(files[b.ROOT+"/"+rel]).read()).hexdigest()==digest
    with pytest.raises(b.PackageDenied,match="OUTPUT_NOT_UNIQUE"):
        b.make_packet(candidate="b"*40,rollback="a"*40,output=out)


def test_packet_rejects_outside_directory_and_wrong_rev(tmp_path,monkeypatch):
    monkeypatch.setattr(b,"ARTIFACTS",tmp_path)
    with pytest.raises(b.PackageDenied):
        b.make_packet(candidate="main",rollback="a"*40,
                      output=tmp_path/"bad")
    with pytest.raises(b.PackageDenied):
        b.make_packet(candidate="b"*40,rollback="a"*40,
                      output=tmp_path/"unreviewed")
    with pytest.raises(b.PackageDenied):
        b.make_packet(candidate="b"*40,rollback="a"*40,
                      output=tmp_path/("pmv4-e-root-admin-bundle-"+"b"*40),
                      source_root=tmp_path)
