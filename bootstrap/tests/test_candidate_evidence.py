from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from bootstrap.candidate_evidence import collect_candidate_readiness_evidence
from bootstrap.candidate_ready import evaluate_candidate_ready
from bootstrap.install_runtime import load_resources
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
NOW = 1800000000.0


def config():
    return json.loads(
        (ROOT / "config/examples/msp-configuration.example.json").read_text()
    )


def resources():
    return load_resources(
        ROOT / "config/bootstrap-resources.v1.json",
        ROOT / "config/schemas/bootstrap-resources.schema.json",
    )


def schema():
    return json.loads(
        (ROOT / "config/schemas/candidate-readiness-evidence.schema.json").read_text()
    )


def prepare_root(tmp_path: Path):
    root = tmp_path / "candidate"
    state = root / "var/lib/jason"
    (state / "openclaw").mkdir(parents=True)
    manifest = build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-jason-b",
            instance_id="jason-b",
            environment="candidate",
            release_version="0.1.0",
            source_sha="a" * 40,
            artifact_digest="sha256:" + "b" * 64,
            deployment_revision="c" * 64,
            msp_configuration_revision="d" * 64,
            msp_policy_revision="e" * 64,
            playbook_revision="f" * 64,
            components=(
                ComponentIdentity(
                    name="core",
                    kind="runtime",
                    required=True,
                    release_version="0.1.0",
                    source_sha="a" * 40,
                    artifact_digest="sha256:" + "b" * 64,
                ),
            ),
            schemas=(SchemaIdentity("authority", "sha256:" + "1" * 64),),
            providers=(
                ProviderIdentity("autotask", True, "bundle"),
                ProviderIdentity("datto_rmm", True, "bundle"),
            ),
            runtime=RuntimeIdentity(
                os="ubuntu 24.04",
                architecture="x86_64",
                python="3.12.3",
                container_runtime="Docker 29",
                compose="5",
            ),
        )
    )
    (state / "deployment-manifest.json").write_text(json.dumps(manifest))
    (state / "candidate-bootstrap-result.json").write_text(
        json.dumps({"readiness": {"status": "ready_for_runtime_activation"}})
    )
    gov = state / "openclaw/operational-health.json"
    gov.write_text(json.dumps({"status": "pass"}))
    os.utime(gov, (NOW - 10, NOW - 10))
    (state / "provider-health-canaries.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at_epoch": NOW - 10,
                "results": [
                    {
                        "provider": "autotask",
                        "capability": "service.company.search",
                        "healthy": True,
                    },
                    {
                        "provider": "datto_rmm",
                        "capability": "endpoint.device.search",
                        "healthy": True,
                    },
                ],
            }
        )
    )
    attestation = state / "secret-presence-attestation.json"
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contains_secret_values": False,
                "available_references": [
                    "autotask.readonly",
                    "datto_rmm.readonly",
                ],
            }
        )
    )
    return root, attestation, manifest


def runner(command):
    command = tuple(command)
    if command[:3] == ("docker", "network", "inspect"):
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")
    if command[:2] == ("systemctl", "is-enabled"):
        return SimpleNamespace(returncode=0, stdout="enabled\n", stderr="")
    raise AssertionError(command)


def test_collected_evidence_can_drive_ready(tmp_path):
    root, attestation, manifest = prepare_root(tmp_path)

    def http_getter(url):
        assert url == "http://127.0.0.1:8080/healthz"
        return 200, {
            "status": "ok",
            "deployment_identity_sha256": manifest["identity_sha256"],
        }

    evidence = collect_candidate_readiness_evidence(
        target_root=root,
        resources=resources(),
        msp_configuration=config(),
        secret_presence_attestation_path=attestation,
        runtime_health_url="http://127.0.0.1:8080/healthz",
        runner=runner,
        http_getter=http_getter,
        now_epoch=NOW,
    )
    result = evaluate_candidate_ready(
        target_root=root,
        resources=resources(),
        msp_configuration=config(),
        evidence=evidence,
        evidence_schema=schema(),
    )
    assert result.status == "READY"
    assert evidence["governance_health"]["status"] == "healthy"
    assert set(evidence["providers"].values()) == {"ready"}


def test_stale_governance_and_provider_evidence_blocks_ready(tmp_path):
    root, attestation, manifest = prepare_root(tmp_path)

    def http_getter(url):
        return 200, {
            "status": "ok",
            "deployment_identity_sha256": manifest["identity_sha256"],
        }

    evidence = collect_candidate_readiness_evidence(
        target_root=root,
        resources=resources(),
        msp_configuration=config(),
        secret_presence_attestation_path=attestation,
        runtime_health_url="http://127.0.0.1:8080/healthz",
        runner=runner,
        http_getter=http_getter,
        now_epoch=NOW + 3600,
        governance_max_age_seconds=60,
        provider_max_age_seconds=60,
    )
    result = evaluate_candidate_ready(
        target_root=root,
        resources=resources(),
        msp_configuration=config(),
        evidence=evidence,
        evidence_schema=schema(),
    )
    assert result.status == "BLOCKED"
    assert "governance_health_not_healthy" in result.blockers
    assert "provider_not_ready:autotask" in result.blockers
    assert "provider_not_ready:datto_rmm" in result.blockers


def test_runtime_health_unavailable_blocks_ready(tmp_path):
    root, attestation, _ = prepare_root(tmp_path)

    evidence = collect_candidate_readiness_evidence(
        target_root=root,
        resources=resources(),
        msp_configuration=config(),
        secret_presence_attestation_path=attestation,
        runtime_health_url="http://127.0.0.1:8080/healthz",
        runner=runner,
        http_getter=lambda url: (0, {}),
        now_epoch=NOW,
    )
    result = evaluate_candidate_ready(
        target_root=root,
        resources=resources(),
        msp_configuration=config(),
        evidence=evidence,
        evidence_schema=schema(),
    )
    assert result.status == "BLOCKED"
    assert "runtime_health_not_healthy" in result.blockers
