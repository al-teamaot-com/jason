from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest

from bootstrap.install_runtime import (
    BootstrapRuntimeError,
    evaluate_candidate_readiness,
    initialize_state_stores,
    load_resources,
    stage_portable_systemd_units,
    stage_release_archive,
    write_bootstrap_runtime_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
RESOURCE_DOC = ROOT / "config/bootstrap-resources.v1.json"
RESOURCE_SCHEMA = ROOT / "config/schemas/bootstrap-resources.schema.json"


def resources():
    return load_resources(RESOURCE_DOC, RESOURCE_SCHEMA)


def release_archive(tmp_path: Path, *, unsafe: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "release.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        files = {
            "../escape" if unsafe else "README.txt": b"release",
        }
        if not unsafe:
            files.update(
                {
                    "tools/delegation_maintenance.py": b"print('synthetic')\n",
                    "tools/openclaw_authority_health_snapshot.py": b"print('synthetic')\n",
                }
            )
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, digest


def test_resource_inventory_is_schema_valid():
    document = resources()
    assert document["schema_version"] == "1.0"
    assert any(item["name"] == "jason-core" for item in document["networks"])


def test_release_staging_verifies_digest_and_creates_atomic_current_link(tmp_path):
    archive, digest = release_archive(tmp_path)
    target = tmp_path / "candidate-root"
    result = stage_release_archive(
        archive_path=archive,
        expected_artifact_sha256=digest,
        source_sha="a" * 40,
        target_root=target,
    )
    assert Path(result.release_path, "README.txt").read_bytes() == b"release"
    current = Path(result.current_link)
    assert current.is_symlink()
    assert current.resolve() == Path(result.release_path)


def test_release_staging_rejects_digest_mismatch_and_unsafe_members(tmp_path):
    archive, _ = release_archive(tmp_path)
    with pytest.raises(BootstrapRuntimeError, match="SHA-256 mismatch"):
        stage_release_archive(
            archive_path=archive,
            expected_artifact_sha256="0" * 64,
            source_sha="a" * 40,
            target_root=tmp_path / "bad-digest",
        )
    unsafe, digest = release_archive(tmp_path / "unsafe", unsafe=True)
    with pytest.raises(BootstrapRuntimeError, match="unsafe path"):
        stage_release_archive(
            archive_path=unsafe,
            expected_artifact_sha256=digest,
            source_sha="b" * 40,
            target_root=tmp_path / "bad-archive",
        )


def test_core_state_stores_use_real_jason_initializers(tmp_path):
    target = tmp_path / "candidate-root"
    result = initialize_state_stores(target_root=target, resources=resources())
    by_id = {item.store_id: item for item in result}
    for store_id in (
        "identity-authority",
        "client-boundaries",
        "orchestration-events",
        "approval-continuations",
    ):
        assert by_id[store_id].status == "initialized"

    authority = target / "var/lib/jason/authority/authority.sqlite3"
    with sqlite3.connect(authority) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )
        }
    assert "identities" in tables
    assert "authority_grants" in tables

    runtime_owned = target / "var/lib/jason/openclaw/model-usage.sqlite3"
    assert not runtime_owned.exists()
    assert runtime_owned.parent.is_dir()


def test_systemd_staging_copies_only_declared_portable_units(tmp_path):
    target = tmp_path / "candidate-root"
    staged = stage_portable_systemd_units(
        repository_root=ROOT,
        target_root=target,
        resources=resources(),
    )
    statuses = {item.source: item.status for item in staged}
    assert statuses[
        "infrastructure/openclaw-operations/systemd/jason-delegation-maintenance.service"
    ] == "staged"
    assert statuses[
        "infrastructure/kfs-collector/systemd/jason-kfs-collector.service"
    ] == "blocked_nonportable"
    assert not (target / "etc/systemd/system/jason-kfs-collector.service").exists()


def test_readiness_reaches_runtime_activation_boundary_without_activating(tmp_path):
    target = tmp_path / "candidate-root"
    archive, digest = release_archive(tmp_path)
    release = stage_release_archive(
        archive_path=archive,
        expected_artifact_sha256=digest,
        source_sha="a" * 40,
        target_root=target,
    )
    state = initialize_state_stores(target_root=target, resources=resources())
    services = stage_portable_systemd_units(
        repository_root=ROOT,
        target_root=target,
        resources=resources(),
    )
    write_bootstrap_runtime_manifest(
        target_root=target,
        release=release,
        state=state,
        services=services,
        resources=resources(),
    )
    readiness = evaluate_candidate_readiness(
        target_root=target,
        resources=resources(),
    )
    assert readiness["status"] == "ready_for_runtime_activation"
    assert readiness["service_activation_performed"] is False
    assert readiness["provider_secret_enrollment_performed"] is False
    assert "jason-core" in readiness["network_activation_required"]


def test_live_root_is_refused_for_mutating_bootstrap_operations(tmp_path):
    archive, digest = release_archive(tmp_path)
    with pytest.raises(PermissionError):
        stage_release_archive(
            archive_path=archive,
            expected_artifact_sha256=digest,
            source_sha="a" * 40,
            target_root="/",
        )
    with pytest.raises(PermissionError):
        initialize_state_stores(target_root="/", resources=resources())

def test_readiness_blocks_when_staged_service_target_is_missing_from_release(tmp_path):
    target = tmp_path / "candidate-root"
    archive, digest = release_archive(tmp_path)
    release = stage_release_archive(
        archive_path=archive,
        expected_artifact_sha256=digest,
        source_sha="c" * 40,
        target_root=target,
    )
    state = initialize_state_stores(target_root=target, resources=resources())
    services = stage_portable_systemd_units(
        repository_root=ROOT,
        target_root=target,
        resources=resources(),
    )
    write_bootstrap_runtime_manifest(
        target_root=target,
        release=release,
        state=state,
        services=services,
        resources=resources(),
    )
    missing = target / "opt/jason/current/tools/delegation_maintenance.py"
    missing.unlink()

    readiness = evaluate_candidate_readiness(
        target_root=target,
        resources=resources(),
    )
    assert readiness["status"] == "blocked"
    assert (
        "release_service_target_missing:/opt/jason/current/tools/delegation_maintenance.py"
        in readiness["blockers"]
    )
