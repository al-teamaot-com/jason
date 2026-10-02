from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bootstrap.candidate_host import CandidateHostIdentity
from bootstrap.candidate_runtime import (
    CandidateRuntimeError,
    build_candidate_runtime_plan,
    execute_candidate_runtime_start,
    load_candidate_runtime_config,
)
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)


ROOT = Path(__file__).resolve().parents[2]


def identity():
    return CandidateHostIdentity(
        schema_version="1.0",
        environment="candidate",
        instance_id="jason-b",
        bootstrap_authorized=True,
    )


def config():
    return load_candidate_runtime_config(
        ROOT / "config/candidate-runtime.v1.json",
        ROOT / "config/schemas/candidate-runtime.schema.json",
    )


def prepare_root(tmp_path: Path):
    root = tmp_path / "candidate"
    release = root / "opt/jason/releases" / ("a" * 40)
    compose = release / "infrastructure/jason-runtime/compose.yaml"
    compose.parent.mkdir(parents=True)
    compose.write_text("services:\n  jason-runtime:\n    image: placeholder\n")
    current = root / "opt/jason/current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(Path("releases") / ("a" * 40))

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
            schemas=(SchemaIdentity("authority", "1"),),
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
        ),
        generated_at=datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc),
    )
    manifest_path = root / "var/lib/jason/deployment-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest))

    attestation = root / "var/lib/jason/secret-presence-attestation.json"
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
    env = root / "etc/jason/runtime.env"
    env.parent.mkdir(parents=True)
    env_lines = [
        "JASON_SES_DEFAULT_SENDER=test@example.invalid",
        "JASON_OLLAMA_MODEL=qwen-test",
    ]
    for index, item in enumerate(config()["secret_mounts"]):
        source = root / "var/lib/jason/runtime-secrets/test" / str(index)
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("synthetic")
        source.chmod(0o600)
        env_lines.append(
            str(item["environment_variable"]) + "=" + str(source)
        )
    env.write_text("\n".join(env_lines) + "\n")
    env.chmod(0o640)

    msp = {
        "providers": {
            "autotask": {
                "enabled": True,
                "secret_reference": "autotask.readonly",
            },
            "datto_rmm": {
                "enabled": True,
                "secret_reference": "datto_rmm.readonly",
            },
        }
    }
    return root, manifest, attestation, env, msp


def test_candidate_runtime_plan_uses_candidate_overlay_and_complete_secrets(tmp_path):
    root, manifest, attestation, env, msp = prepare_root(tmp_path)
    plan = build_candidate_runtime_plan(
        target_root=root,
        candidate_identity=identity(),
        runtime_config=config(),
        msp_configuration=msp,
        secret_presence_attestation_path=attestation,
        env_file=env,
    )
    assert plan.container_name == "jason-runtime-candidate"
    assert plan.image == "jason-runtime:candidate-" + ("a" * 12)
    assert plan.deployment_identity_sha256 == manifest["identity_sha256"]
    overlay = Path(plan.overlay_file).read_text()
    assert "jason-runtime-candidate" in overlay
    assert "restart: \"no\"" in overlay
    assert "127.0.0.1:18080:8080" in overlay
    assert "volumes: !override" in overlay
    assert "/run/jason-secrets/openbao/role_id:ro" in overlay
    assert "/run/jason-secrets/openbao/autotask/secret_id:ro" in overlay
    assert plan.host_health_port == 18080
    assert plan.health_url == "http://127.0.0.1:18080/healthz"
    assert "production-deploy.sh" not in overlay


def test_missing_secret_reference_blocks_runtime_plan(tmp_path):
    root, _, attestation, env, msp = prepare_root(tmp_path)
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contains_secret_values": False,
                "available_references": ["autotask.readonly"],
            }
        )
    )
    with pytest.raises(CandidateRuntimeError, match="required secret references"):
        build_candidate_runtime_plan(
            target_root=root,
            candidate_identity=identity(),
            runtime_config=config(),
            msp_configuration=msp,
            secret_presence_attestation_path=attestation,
            env_file=env,
        )


def test_runtime_start_validates_compose_creates_networks_and_requires_manifest_health(tmp_path):
    root, manifest, attestation, env, msp = prepare_root(tmp_path)
    plan = build_candidate_runtime_plan(
        target_root=root,
        candidate_identity=identity(),
        runtime_config=config(),
        msp_configuration=msp,
        secret_presence_attestation_path=attestation,
        env_file=env,
    )
    calls = []

    def runner(command):
        calls.append(tuple(command))
        if command[:3] == ("docker", "network", "inspect"):
            return SimpleNamespace(returncode=1, stdout="", stderr="missing")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = execute_candidate_runtime_start(
        plan=plan,
        candidate_identity=identity(),
        runner=runner,
        http_getter=lambda url: (
            200,
            {
                "status": "ok",
                "deployment_identity_sha256": manifest["identity_sha256"],
            },
        ),
        health_timeout_seconds=0.1,
        poll_interval_seconds=0.001,
    )
    assert result["status"] == "runtime_healthy"
    assert result["production_deploy_script_used"] is False
    assert any(
        call[:3] == ("docker", "compose", "--project-name")
        and "config" in call
        for call in calls
    )
    assert any(
        call[:3] == ("docker", "compose", "--project-name")
        and "up" in call
        for call in calls
    )
    assert not any("production-deploy.sh" in " ".join(call) for call in calls)


def test_runtime_health_identity_mismatch_times_out(tmp_path):
    root, _, attestation, env, msp = prepare_root(tmp_path)
    plan = build_candidate_runtime_plan(
        target_root=root,
        candidate_identity=identity(),
        runtime_config=config(),
        msp_configuration=msp,
        secret_presence_attestation_path=attestation,
        env_file=env,
    )
    with pytest.raises(CandidateRuntimeError, match="health did not become ready"):
        execute_candidate_runtime_start(
            plan=plan,
            candidate_identity=identity(),
            runner=lambda command: SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
            http_getter=lambda url: (
                200,
                {
                    "status": "ok",
                    "deployment_identity_sha256": "0" * 64,
                },
            ),
            health_timeout_seconds=0,
            poll_interval_seconds=0,
        )


def test_health_port_and_url_must_match(tmp_path):
    root, _, attestation, env, msp = prepare_root(tmp_path)
    runtime = config()
    runtime["runtime_health_url"] = "http://127.0.0.1:9999/healthz"
    with pytest.raises(
        CandidateRuntimeError,
        match="health URL does not match",
    ):
        build_candidate_runtime_plan(
            target_root=root,
            candidate_identity=identity(),
            runtime_config=runtime,
            msp_configuration=msp,
            secret_presence_attestation_path=attestation,
            env_file=env,
        )


def test_missing_candidate_mount_file_blocks_runtime_plan(tmp_path):
    root, _, attestation, env, msp = prepare_root(tmp_path)
    runtime = config()
    variable = runtime["secret_mounts"][0]["environment_variable"]
    lines = env.read_text().splitlines()
    rewritten = []
    for line in lines:
        if line.startswith(variable + "="):
            rewritten.append(variable + "=" + str(root / "missing"))
        else:
            rewritten.append(line)
    env.write_text("\n".join(rewritten) + "\n")
    with pytest.raises(
        CandidateRuntimeError,
        match="candidate mount .* is unavailable",
    ):
        build_candidate_runtime_plan(
            target_root=root,
            candidate_identity=identity(),
            runtime_config=runtime,
            msp_configuration=msp,
            secret_presence_attestation_path=attestation,
            env_file=env,
        )
