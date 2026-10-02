from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tarfile

from bootstrap.candidate_bootstrap import bootstrap_candidate
from bootstrap.candidate_ready import evaluate_candidate_ready
from bootstrap.clean_install import HostObservation
from bootstrap.install_runtime import load_resources


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


def candidate(tmp_path: Path):
    archive, digest = make_release(tmp_path)
    target = tmp_path / "jason-b"
    config_path = ROOT / "config/examples/msp-configuration.example.json"
    boot = bootstrap_candidate(
        target_root=target,
        release_archive=archive,
        release_artifact_sha256=digest,
        source_sha="a" * 40,
        msp_configuration_path=config_path,
        msp_policy_path=ROOT / "config/examples/msp-policy.example.json",
        schema_root=ROOT / "config/schemas",
        resources_path=ROOT / "config/bootstrap-resources.v1.json",
        resources_schema_path=ROOT / "config/schemas/bootstrap-resources.schema.json",
        repository_root=ROOT,
        instance_id="jason-b",
        host=host(),
    )
    manifest = json.loads(
        (target / "var/lib/jason/deployment-manifest.json").read_text()
    )
    resources = load_resources(
        ROOT / "config/bootstrap-resources.v1.json",
        ROOT / "config/schemas/bootstrap-resources.schema.json",
    )
    config = json.loads(config_path.read_text())
    schema = json.loads(
        (ROOT / "config/schemas/candidate-readiness-evidence.schema.json").read_text()
    )
    evidence = {
        "schema_version": "1.0",
        "instance_id": "jason-b",
        "deployment_identity_sha256": manifest["identity_sha256"],
        "bootstrap_status": boot["readiness"]["status"],
        "available_secret_references": [
            "autotask.readonly",
            "datto_rmm.readonly"
        ],
        "networks": {
            "jason-core": "present",
            "jason-observability": "present"
        },
        "units": {
            "jason-delegation-maintenance.service": "enabled",
            "jason-delegation-maintenance.timer": "enabled",
            "jason-openclaw-authority-health.service": "enabled",
            "jason-openclaw-authority-health.timer": "enabled"
        },
        "runtime_health": {
            "status": "healthy",
            "deployment_identity_sha256": manifest["identity_sha256"]
        },
        "governance_health": {"status": "healthy"},
        "providers": {
            "autotask": "ready",
            "datto_rmm": "ready"
        }
    }
    return target, resources, config, schema, evidence


def test_candidate_ready_requires_all_checks(tmp_path):
    target, resources, config, schema, evidence = candidate(tmp_path)
    result = evaluate_candidate_ready(
        target_root=target,
        resources=resources,
        msp_configuration=config,
        evidence=evidence,
        evidence_schema=schema,
    )
    assert result.status == "READY"
    assert not result.blockers
    assert set(result.checks.values()) == {"pass"}


def test_missing_secret_blocks_ready(tmp_path):
    target, resources, config, schema, evidence = candidate(tmp_path)
    evidence["available_secret_references"] = ["autotask.readonly"]
    result = evaluate_candidate_ready(
        target_root=target,
        resources=resources,
        msp_configuration=config,
        evidence=evidence,
        evidence_schema=schema,
    )
    assert result.status == "BLOCKED"
    assert "secret_missing:datto_rmm.readonly" in result.blockers


def test_runtime_identity_mismatch_blocks_ready(tmp_path):
    target, resources, config, schema, evidence = candidate(tmp_path)
    evidence["runtime_health"]["deployment_identity_sha256"] = "b" * 64
    result = evaluate_candidate_ready(
        target_root=target,
        resources=resources,
        msp_configuration=config,
        evidence=evidence,
        evidence_schema=schema,
    )
    assert result.status == "BLOCKED"
    assert "runtime_manifest_identity_mismatch" in result.blockers


def test_governance_or_provider_failure_blocks_ready(tmp_path):
    target, resources, config, schema, evidence = candidate(tmp_path)
    evidence["governance_health"]["status"] = "unhealthy"
    evidence["providers"]["autotask"] = "degraded"
    result = evaluate_candidate_ready(
        target_root=target,
        resources=resources,
        msp_configuration=config,
        evidence=evidence,
        evidence_schema=schema,
    )
    assert result.status == "BLOCKED"
    assert "governance_health_not_healthy" in result.blockers
    assert "provider_not_ready:autotask" in result.blockers


def test_missing_unit_and_network_block_ready(tmp_path):
    target, resources, config, schema, evidence = candidate(tmp_path)
    evidence["networks"]["jason-core"] = "missing"
    evidence["units"]["jason-delegation-maintenance.timer"] = "disabled"
    result = evaluate_candidate_ready(
        target_root=target,
        resources=resources,
        msp_configuration=config,
        evidence=evidence,
        evidence_schema=schema,
    )
    assert result.status == "BLOCKED"
    assert "network_missing:jason-core" in result.blockers
    assert "unit_not_enabled:jason-delegation-maintenance.timer" in result.blockers

def test_live_root_ready_evaluation_requires_candidate_identity():
    from bootstrap.candidate_activation import CandidateHostIdentity
    from bootstrap.candidate_ready import CandidateReadinessError

    # Validation reaches the root guard before attempting manifest reads.
    try:
        evaluate_candidate_ready(
            target_root="/",
            resources={"systemd_units": [], "networks": []},
            msp_configuration={"providers": {}},
            evidence={},
            evidence_schema={"type": "object"},
        )
    except PermissionError as exc:
        assert "candidate host identity" in str(exc)
    else:
        raise AssertionError("live-root evaluation must require candidate identity")

    invalid = CandidateHostIdentity(
        schema_version="1.0",
        environment="production",
        instance_id="prod",
        bootstrap_authorized=True,
    )
    try:
        evaluate_candidate_ready(
            target_root="/",
            resources={"systemd_units": [], "networks": []},
            msp_configuration={"providers": {}},
            evidence={},
            evidence_schema={"type": "object"},
            candidate_identity=invalid,
        )
    except PermissionError as exc:
        assert "authorized candidate host" in str(exc)
    else:
        raise AssertionError("production identity must not unlock candidate READY")
