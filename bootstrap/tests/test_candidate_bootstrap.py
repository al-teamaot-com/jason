from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile

from bootstrap.candidate_bootstrap import bootstrap_candidate
from bootstrap.clean_install import HostObservation


ROOT = Path(__file__).resolve().parents[2]


def host():
    return HostObservation(
        os_id="ubuntu",
        os_version="24.04",
        architecture="x86_64",
        python_version="3.12.3",
        docker_version="Docker version 29.6.2",
        compose_version="Docker Compose version v5.3.1",
    )


def make_release(tmp_path: Path):
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        files = {
            "release.txt": b"synthetic released Jason",
            "tools/delegation_maintenance.py": b"print('synthetic')\n",
            "tools/openclaw_authority_health_snapshot.py": b"print('synthetic')\n",
        }
        for name, content in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(content)
            handle.addfile(item, io.BytesIO(content))
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_end_to_end_candidate_bootstrap_reaches_activation_boundary(tmp_path):
    release, digest = make_release(tmp_path)
    target = tmp_path / "jason-b"

    result = bootstrap_candidate(
        target_root=target,
        release_archive=release,
        release_artifact_sha256=digest,
        source_sha="a" * 40,
        msp_configuration_path=ROOT / "config/examples/msp-configuration.example.json",
        msp_policy_path=ROOT / "config/examples/msp-policy.example.json",
        schema_root=ROOT / "config/schemas",
        resources_path=ROOT / "config/bootstrap-resources.v1.json",
        resources_schema_path=ROOT / "config/schemas/bootstrap-resources.schema.json",
        repository_root=ROOT,
        host=host(),
    )

    assert result["readiness"]["status"] == "ready_for_runtime_activation"
    assert result["readiness"]["service_activation_performed"] is False
    assert result["readiness"]["provider_secret_enrollment_performed"] is False

    assert (target / "opt/jason/current/release.txt").read_bytes() == b"synthetic released Jason"
    assert (target / "etc/jason/msp-configuration.json").is_file()
    assert (target / "etc/jason/msp-policy.json").is_file()
    assert (target / "var/lib/jason/bootstrap-runtime.json").is_file()
    assert (target / "var/lib/jason/candidate-bootstrap-result.json").is_file()

    with sqlite3.connect(target / "var/lib/jason/authority/authority.sqlite3") as db:
        assert db.execute(
            "select count(*) from sqlite_master where type='table' and name='identities'"
        ).fetchone()[0] == 1

    installed_units = {path.name for path in (target / "etc/systemd/system").glob("*")}
    assert "jason-delegation-maintenance.service" in installed_units
    assert "jason-kfs-collector.service" not in installed_units

    serialized = json.dumps(result)
    assert "/home/al/" not in serialized
