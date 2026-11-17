"""Offline root-install scope tests. No production files or credentials used."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from tools.catalog_scoped_promotion_bundle import FILES
from tools.catalog_scoped_root_install_preflight import (
    CatalogRootPreflightDenied,
    EXACT_FILE_SET,
    ROOT_WORKER,
    _canonical,
    inspect_staged_exact_bundle,
    preflight_live,
)

SOURCE_SHA = "a" * 40


def staged_fixture(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir(mode=0o700)
    content = {name: (b"reviewed immutable source " + name.encode()) for name in FILES}
    manifest = {
        "schema_version": "1.0",
        "status": "source_only_not_installed",
        "source_sha": SOURCE_SHA,
        "release_approval_recorded": False,
        "production_mutations": False,
        "root_installation_authorized": False,
        "files": {
            key: {"sha256": sha256(content[key]).hexdigest(), "bytes": len(content[key])}
            for key in sorted(content)
        },
    }
    digest = sha256(_canonical(manifest)).hexdigest()
    manifest["bundle_sha256"] = digest
    for name, raw in content.items():
        path = stage / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o644)
    doc = stage / "SOURCE_ONLY_MANIFEST.json"
    doc.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    doc.chmod(0o600)
    return stage, digest, content


def inspect(stage, digest, content):
    return inspect_staged_exact_bundle(
        stage, expected_source_sha=SOURCE_SHA, expected_bundle_sha256=digest,
        committed_blob=lambda name: content[name],
    )


def test_pure_exact_scoped_package_and_no_install_entrypoint(tmp_path):
    stage, digest, content = staged_fixture(tmp_path)
    plan = inspect(stage, digest, content)
    assert plan["source_sha"] == SOURCE_SHA
    assert plan["installer_not_present"] is True
    assert plan["file_count"] == 17
    assert set(content) == EXACT_FILE_SET
    assert len({x["root_target"] for x in plan["targets"]}) == 17
    assert next(x for x in plan["targets"]
                if x["source_relative"] == "tools/release_host_reconcile_worker.py")[
                    "root_target"
                ] == str(ROOT_WORKER)


@pytest.mark.parametrize("name", [
    "tools/catalog_scoped_promotion_host.py",
    "tools/release_host_reconcile_worker.py",
    "implementation/kernel/signed_owner_release.py",
])
def test_stage_or_git_byte_drift_fails(tmp_path, name):
    stage, digest, content = staged_fixture(tmp_path)
    (stage / name).write_bytes(b"tampered")
    with pytest.raises(CatalogRootPreflightDenied, match="STAGED_FILE_OR_GIT_BLOB_CHANGED"):
        inspect(stage, digest, content)
    (stage / name).write_bytes(content[name])
    content[name] = b"wrong git blob"
    with pytest.raises(CatalogRootPreflightDenied, match="STAGED_FILE_OR_GIT_BLOB_CHANGED"):
        inspect(stage, digest, content)


def test_no_symlink_source_files(tmp_path):
    stage, digest, content = staged_fixture(tmp_path)
    path = stage / FILES[0]
    path.unlink()
    path.symlink_to(stage / FILES[1])
    with pytest.raises(CatalogRootPreflightDenied, match="FILE_MISSING_OR_SYMLINK"):
        inspect(stage, digest, content)


@pytest.mark.parametrize("field,value", [
    ("production_mutations", True),
    ("root_installation_authorized", True),
    ("release_approval_recorded", True),
    ("status", "installed"),
    ("source_sha", "b" * 40),
])
def test_manifest_does_not_infer_approval_or_new_source(tmp_path, field, value):
    stage, digest, content = staged_fixture(tmp_path)
    doc = stage / "SOURCE_ONLY_MANIFEST.json"
    parsed = json.loads(doc.read_text())
    parsed[field] = value
    doc.write_text(json.dumps(parsed))
    with pytest.raises(CatalogRootPreflightDenied, match="MANIFEST_CONTRACT_CHANGED"):
        inspect(stage, digest, content)


def test_digest_replay_and_missing_scope_denied(tmp_path):
    stage, digest, content = staged_fixture(tmp_path)
    with pytest.raises(CatalogRootPreflightDenied, match="MANIFEST_CONTRACT_CHANGED"):
        inspect(stage, "f" * 64, content)
    doc = stage / "SOURCE_ONLY_MANIFEST.json"
    parsed = json.loads(doc.read_text())
    del parsed["files"][FILES[0]]
    prior = {k: v for k, v in parsed.items() if k != "bundle_sha256"}
    parsed["bundle_sha256"] = sha256(_canonical(prior)).hexdigest()
    doc.write_text(json.dumps(parsed))
    with pytest.raises(CatalogRootPreflightDenied, match="STAGED_SOURCE_SCOPE_INVALID"):
        inspect(stage, parsed["bundle_sha256"], content)


def test_source_only_package_must_be_private_and_owned(tmp_path):
    stage, digest, content = staged_fixture(tmp_path)
    stage.chmod(0o755)
    with pytest.raises(CatalogRootPreflightDenied, match="STAGE_OWNER_OR_MODE"):
        inspect(stage, digest, content)


def test_host_preflight_rejects_nonprotected_git_source_before_any_host_access(
    tmp_path, monkeypatch
):
    import tools.catalog_scoped_root_install_preflight as module
    stage, digest, _ = staged_fixture(tmp_path)
    monkeypatch.setattr(
        module, "_git",
        lambda _repo, *args: b"b" * 40 + b" refs/heads/main\n"
        if args[0] == "ls-remote" else b"",
    )
    with pytest.raises(CatalogRootPreflightDenied, match="PROTECTED_MAIN_CHANGED"):
        preflight_live(
            repo=tmp_path, stage=stage, expected_source_sha=SOURCE_SHA,
            expected_bundle_sha256=digest, old_worker_sha256="1" * 64,
        )


def test_bad_source_sha_denied_before_blob_checks(tmp_path):
    stage, digest, content = staged_fixture(tmp_path)
    with pytest.raises(CatalogRootPreflightDenied, match="SOURCE_SHA_INVALID"):
        inspect_staged_exact_bundle(
            stage, expected_source_sha="bad", expected_bundle_sha256=digest,
            committed_blob=lambda name: content[name],
        )
