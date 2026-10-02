from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tarfile

from jsonschema import Draft202012Validator

from bootstrap.candidate_bootstrap import bootstrap_candidate
from bootstrap.candidate_manifest import (
    generate_candidate_deployment_manifest,
)
from bootstrap.clean_install import HostObservation
from bootstrap.install_runtime import load_resources
from jason_runtime.deployment_identity import FileDeploymentManifestProvider


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)


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
    files = {
        "implementation/pyproject.toml": (
            b'[project]\nname = "jason-platform"\nversion = "0.1.0"\n'
        ),
        "implementation/autonomous_remediation/playbook_registry.json": (
            b'{"schema_version":"1.0","playbooks":[]}\n'
        ),
        "tools/delegation_maintenance.py": b"print('synthetic')\n",
        "tools/openclaw_authority_health_snapshot.py": b"print('synthetic')\n",
    }
    with tarfile.open(archive, "w:gz") as handle:
        for name, content in files.items():
            item = tarfile.TarInfo(name)
            item.size = len(content)
            handle.addfile(item, io.BytesIO(content))
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_candidate_bootstrap_generates_authoritative_deployment_manifest(tmp_path):
    release_archive, digest = make_release(tmp_path)
    target = tmp_path / "jason-b"
    configuration_path = ROOT / "config/examples/msp-configuration.example.json"
    policy_path = ROOT / "config/examples/msp-policy.example.json"

    boot = bootstrap_candidate(
        target_root=target,
        release_archive=release_archive,
        release_artifact_sha256=digest,
        source_sha="a" * 40,
        msp_configuration_path=configuration_path,
        msp_policy_path=policy_path,
        schema_root=ROOT / "config/schemas",
        resources_path=ROOT / "config/bootstrap-resources.v1.json",
        resources_schema_path=ROOT / "config/schemas/bootstrap-resources.schema.json",
        repository_root=ROOT,
        instance_id="jason-b",
        host=host(),
    )
    resources = load_resources(
        ROOT / "config/bootstrap-resources.v1.json",
        ROOT / "config/schemas/bootstrap-resources.schema.json",
    )
    msp_configuration = json.loads(configuration_path.read_text())

    from bootstrap.install_runtime import ReleaseStageResult, StateStoreResult

    release = ReleaseStageResult(**boot["release"])
    stores = tuple(StateStoreResult(**item) for item in boot["state_stores"])

    manifest, output = generate_candidate_deployment_manifest(
        target_root=target,
        instance_id="jason-b",
        release=release,
        state_stores=stores,
        resources=resources,
        msp_configuration=msp_configuration,
        msp_configuration_revision=json.loads(
            (target / "var/lib/jason/deployment-bootstrap.json").read_text()
        )["msp_configuration_revision"],
        msp_policy_revision=json.loads(
            (target / "var/lib/jason/deployment-bootstrap.json").read_text()
        )["msp_policy_revision"],
        host=host(),
        generated_at=NOW,
    )

    schema = json.loads(
        (ROOT / "config/schemas/deployment-manifest.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(manifest)

    assert output == target / "var/lib/jason/deployment-manifest.json"
    assert manifest["environment"] == "candidate"
    assert manifest["instance_id"] == "jason-b"
    assert manifest["platform"]["release_version"] == "0.1.0"
    assert manifest["platform"]["source_sha"] == "a" * 40
    assert manifest["platform"]["artifact_digest"] == "sha256:" + digest
    assert len(manifest["configuration"]["deployment_revision"]) == 64
    assert len(manifest["configuration"]["playbook_revision"]) == 64
    assert {
        item["store"] for item in manifest["schemas"]
    } == {
        "identity-authority",
        "client-boundaries",
        "orchestration-events",
        "approval-continuations",
    }
    assert all(
        item["version"].startswith("sha256:")
        for item in manifest["schemas"]
    )
    assert {item["provider_id"] for item in manifest["providers"]} == {
        "autotask",
        "datto_rmm",
    }

    readback = FileDeploymentManifestProvider(output).read()
    assert readback["identity_sha256"] == manifest["identity_sha256"]


def test_candidate_manifest_identity_does_not_depend_on_target_root(tmp_path):
    release_archive, digest = make_release(tmp_path)
    identities = []
    for name in ("a", "b"):
        target = tmp_path / name
        config_path = ROOT / "config/examples/msp-configuration.example.json"
        policy_path = ROOT / "config/examples/msp-policy.example.json"
        boot = bootstrap_candidate(
            target_root=target,
            release_archive=release_archive,
            release_artifact_sha256=digest,
            source_sha="b" * 40,
            msp_configuration_path=config_path,
            msp_policy_path=policy_path,
            schema_root=ROOT / "config/schemas",
            resources_path=ROOT / "config/bootstrap-resources.v1.json",
            resources_schema_path=ROOT / "config/schemas/bootstrap-resources.schema.json",
            repository_root=ROOT,
            instance_id="same-logical-instance",
            host=host(),
        )
        from bootstrap.install_runtime import ReleaseStageResult, StateStoreResult

        release = ReleaseStageResult(**boot["release"])
        stores = tuple(StateStoreResult(**item) for item in boot["state_stores"])
        bootstrap_identity = json.loads(
            (target / "var/lib/jason/deployment-bootstrap.json").read_text()
        )
        manifest, _ = generate_candidate_deployment_manifest(
            target_root=target,
            instance_id="same-logical-instance",
            release=release,
            state_stores=stores,
            resources=load_resources(
                ROOT / "config/bootstrap-resources.v1.json",
                ROOT / "config/schemas/bootstrap-resources.schema.json",
            ),
            msp_configuration=json.loads(config_path.read_text()),
            msp_configuration_revision=bootstrap_identity[
                "msp_configuration_revision"
            ],
            msp_policy_revision=bootstrap_identity["msp_policy_revision"],
            host=host(),
            generated_at=NOW,
        )
        identities.append(manifest["identity_sha256"])

    assert identities[0] == identities[1]
