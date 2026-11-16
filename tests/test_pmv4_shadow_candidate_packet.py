"""Offline source-only candidate preparation; never touches active PMv4 or PMv3."""
import hashlib
import json
from pathlib import Path

import pytest

from implementation.kernel.signed_owner_release import canonical
from tools import pmv4_shadow_candidate_packet as candidate
from tools.pmv4_shadow_release import EMPTY_BASELINE, ShadowReleaseDenied, bundle_digest, manifest_check


SHA = "a" * 40
IMAGE = "sha256:" + "b" * 64


@pytest.fixture
def scope(tmp_path, monkeypatch):
    parent = tmp_path / "out"
    monkeypatch.setattr(candidate, "ARTIFACT_PARENT", parent)
    return parent / ("pmv4-a1-" + SHA)


def fake_read(sha, name):
    assert sha == SHA
    assert name in candidate.EXACT_SOURCE_FILES
    return (sha + "::" + name).encode()


def test_source_only_exact_candidate_and_no_owner_or_production(scope):
    item = candidate.prepare(source_sha=SHA, image_digest=IMAGE,
                             read_source=fake_read, target=scope,
                             current_main_ok=lambda rev: rev == SHA)
    assert item["status"] == "preproduction_candidate_not_authorized"
    assert item["single_owner_exact_approval_required"] is True
    assert item["production_mutations"] is False
    assert item["shadow_activation_performed"] is False
    assert item["rollback_sha"] == EMPTY_BASELINE
    assert len(item["source_files"]) == 8
    assert set(item["source_files"]) == set(candidate.EXACT_SOURCE_FILES)
    bundle = scope / "release" / "bundle"
    assert bundle_digest(bundle) == item["bundle_sha256"]
    for name in candidate.EXACT_SOURCE_FILES:
        assert (bundle / name).read_bytes() == fake_read(SHA, name)
        assert not (bundle / name).is_symlink()
    manifest = json.loads((scope / "release" / "release-manifest.json").read_text())
    reviewed = json.loads((scope / "reviewed-scope.json").read_text())
    manifest_check(manifest)
    assert manifest["image_digest"] == IMAGE
    assert manifest["rollback_sha"] == EMPTY_BASELINE
    assert manifest["scope_sha256"] == hashlib.sha256(canonical(reviewed)).hexdigest()
    assert item["manifest_sha256"] == hashlib.sha256(canonical(manifest)).hexdigest()
    assert (scope / "evidence.json").exists()
    assert not (scope / "signed-owner-decision.json").exists()


@pytest.mark.parametrize("sha,image", [
    ("a" * 39, IMAGE),
    (SHA, "latest"),
    (SHA, "sha256:" + "g" * 64),
    ("0"*40, "sha256:" + "b"*63),
])
def test_invalid_hashes_do_not_create(scope, sha, image):
    with pytest.raises(ShadowReleaseDenied, match="INVALID"):
        candidate.prepare(source_sha=sha, image_digest=image,
                          read_source=fake_read, target=scope,
                          current_main_ok=lambda rev: True)
    assert not scope.exists()


def test_protected_main_denied_before_any_file_create(scope):
    with pytest.raises(ShadowReleaseDenied, match="PROTECTED_MAIN"):
        candidate.prepare(source_sha=SHA, image_digest=IMAGE,
                          read_source=fake_read, target=scope,
                          current_main_ok=lambda rev: False)
    assert not scope.exists()


def test_source_failure_cleans_only_new_preproduction_artifacts(scope):
    def changed(sha, name):
        if name == "tools/pmv4_shadow_ci.py":
            return None
        return fake_read(sha, name)
    with pytest.raises(ShadowReleaseDenied, match="SOURCE_BLOB"):
        candidate.prepare(source_sha=SHA, image_digest=IMAGE,
                          read_source=changed, target=scope,
                          current_main_ok=lambda rev: True)
    assert not scope.exists()
    assert scope.parent.is_dir()


def test_existing_exact_target_never_overwritten(scope):
    scope.parent.mkdir(parents=True)
    scope.mkdir()
    keep = scope / "prior-immutable-evidence"
    keep.write_text("untouched")
    with pytest.raises(ShadowReleaseDenied, match="UNTRUSTED_PREPRODUCTION_TARGET"):
        candidate.prepare(source_sha=SHA, image_digest=IMAGE,
                          read_source=fake_read, target=scope,
                          current_main_ok=lambda rev: True)
    assert keep.read_text() == "untouched"


def test_bad_target_path_never_written(scope, tmp_path):
    wrong = tmp_path / "unapproved" / ("pmv4-a1-" + SHA)
    with pytest.raises(ShadowReleaseDenied, match="UNTRUSTED"):
        candidate.prepare(source_sha=SHA, image_digest=IMAGE,
                          read_source=fake_read, target=wrong,
                          current_main_ok=lambda rev: True)
    assert not wrong.exists()


def test_github_source_retrieval_denies_unreviewed_path(tmp_path):
    with pytest.raises(ShadowReleaseDenied, match="ALLOWLISTED"):
        candidate.git_file(tmp_path, SHA, "../secret")
    with pytest.raises(ShadowReleaseDenied, match="ALLOWLISTED"):
        candidate.git_file(tmp_path, "x"*40, candidate.EXACT_SOURCE_FILES[0])


def test_offline_derivative_dockerfile_has_no_downloads_or_secrets():
    source = Path(__file__).resolve().parents[1]
    path = source / "infrastructure/pmv4-shadow-image/Dockerfile"
    lines = [x.strip() for x in path.read_text().splitlines()
             if x.strip() and not x.lstrip().startswith("#")]
    assert lines[0] == "ARG BASE_IMAGE=openclaw:local"
    assert lines[1] == "FROM ${BASE_IMAGE}"
    assert lines[2].startswith('LABEL com.aot.jason.component="pmv4-shadow"')
    assert 'com.aot.jason.provider-mutations="disabled"' in path.read_text()
    assert not any(line.split(" ", 1)[0] in {
        "RUN", "COPY", "ADD", "EXPOSE", "ENTRYPOINT", "CMD"
    } for line in lines)
