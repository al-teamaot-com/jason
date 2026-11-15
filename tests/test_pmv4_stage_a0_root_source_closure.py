"""Source-only regression for the exact Stage A0 one-file source repair."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import pmv4_stage_a0_root_source_closure as repair
from tools import pmv4_stage_a0_sparse_source as sparse
from tools import pmv4_stage_a0_sparse_root_stage as rootstage

LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"


@pytest.fixture
def git_blobs():
    return sparse.git_object(Path(__file__).parents[1])


@pytest.fixture
def repair_policy():
    return {
        "candidate_sha": repair.CANDIDATE, "lkg_sha": LKG,
        "freeze_sha256": FREEZE, "file_path": repair.RELATIVE,
        "file_sha256": repair.MISSING_SHA256,
        "original_scope_sha256": repair.ORIGINAL_SCOPE,
        "proposal_sha256": repair.PROPOSAL_SHA256,
    }


def test_install_is_closed_from_source_checkout():
    assert repair.ROOT_SCRIPT == Path("/usr/local/lib/jason/pmv4_stage_a0_root_source_closure.py")
    assert repair.ZERO_WRITE_AUTHORITY_FROM_SOURCE is True
    with pytest.raises(repair.SourceClosureDenied, match="TRUSTED_ROOT_INSTALL_REQUIRED"):
        repair.execute()
    assert repair.main.__name__ == "main"


def test_exact_original_thirteen_and_added_fourteen(git_blobs, repair_policy, monkeypatch):
    monkeypatch.setattr(sparse, "REQUIRED", tuple(x for x in sparse.REQUIRED if x != repair.RELATIVE))
    source = SimpleNamespace(git_object=lambda _repo: git_blobs,
                             source_manifest=sparse.source_manifest)
    stage = SimpleNamespace(REPO=Path(__file__).parents[1])
    prior, after, payload = repair.exact_source_scopes(source, stage, repair_policy)
    assert prior["scope_sha256"] == repair.ORIGINAL_SCOPE
    assert len(prior["files"]) == 13
    assert len(after["files"]) == 14
    assert after["files"][-1] == {
        "path": repair.RELATIVE, "size": 9571,
        "sha256": repair.MISSING_SHA256, "mode": "0444", "uid": 0, "gid": 0,
    }
    assert sha256(payload).hexdigest() == repair.MISSING_SHA256


def test_prior_scope_rejects_injected_fourteenth(git_blobs, repair_policy):
    old_source = SimpleNamespace(git_object=lambda _repo: git_blobs,
                                 source_manifest=lambda *args, **kwargs: {
                                     "scope_sha256": repair.ORIGINAL_SCOPE,
                                     "files": [{"path": repair.RELATIVE}] * 13,
                                 })
    with pytest.raises(repair.SourceClosureDenied, match="PRIOR_SOURCE_SCOPE_DRIFT"):
        repair.exact_source_scopes(old_source, SimpleNamespace(REPO=Path("/tmp")), repair_policy)


def test_requires_missing_file_and_exclusive_immutable_write(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    repair._write_one_exact(dest, payload, test_only=True)
    assert dest.read_bytes() == payload
    assert dest.stat().st_mode & 0o777 == 0o444
    with pytest.raises(repair.SourceClosureDenied, match="EXACT_TARGET"):
        repair._write_one_exact(dest, payload, test_only=True)
    dest.unlink()
    dest.symlink_to(tmp_path / "missing")
    with pytest.raises(repair.SourceClosureDenied, match="EXACT_TARGET"):
        repair._write_one_exact(dest, payload, test_only=True)


def test_partial_failure_rolls_back_only_created_file(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    with pytest.raises(RuntimeError, match="injected"):
        repair._write_one_exact(
            dest, payload, test_only=True,
            after_write=lambda: (_ for _ in ()).throw(RuntimeError("injected")),
        )
    assert not dest.exists()
    assert dest.parent.is_dir()


def test_cannot_replace_foreign_file_during_rollback(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    foreign = b"foreign content"
    def replace_with_foreign():
        dest.unlink()
        dest.write_bytes(foreign)
        raise RuntimeError("foreign")
    with pytest.raises(RuntimeError, match="foreign"):
        repair._write_one_exact(dest, payload, test_only=True, after_write=replace_with_foreign)
    assert dest.read_bytes() == foreign


def test_rejects_wrong_digest_and_non_temp_sandbox(tmp_path, git_blobs):
    dest = tmp_path / "release" / "tools" / Path(repair.RELATIVE).name
    dest.parent.mkdir(parents=True)
    dest.parent.chmod(0o755)
    payload = git_blobs(repair.CANDIDATE, repair.RELATIVE)
    with pytest.raises(repair.SourceClosureDenied, match="EXACT_TARGET"):
        repair._write_one_exact(dest, payload + b"tampered", test_only=True)
    with pytest.raises(repair.SourceClosureDenied, match="PRODUCTION_ROOT_REQUIRED"):
        repair._write_one_exact(dest, payload, test_only=False)


def test_scope_binds_only_one_file(repair_policy):
    scope = repair.repair_scope(repair_policy)
    assert len(scope) == 64
    assert repair.repair_scope({**repair_policy, "proposal_sha256": "0" * 64}) != scope
    assert repair.repair_scope({**repair_policy, "file_sha256": "0" * 64}) != scope
