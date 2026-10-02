from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

from bootstrap.candidate_host import CandidateHostIdentity
from bootstrap.candidate_mcp import (
    build_candidate_mcp_plan,
    execute_candidate_mcp_start,
    load_candidate_mcp_config,
    run_candidate_provider_canaries,
    validate_candidate_mcp_environment,
)
from bootstrap.candidate_runtime import (
    build_candidate_runtime_plan,
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


def prepare(tmp_path: Path):
    root = tmp_path / "candidate"
    source_sha = "a" * 40
    release = root / "opt/jason/releases" / source_sha
    compose = release / "infrastructure/jason-runtime/compose.yaml"
    dockerfile = release / "infrastructure/jason-mcp/Dockerfile"
    compose.parent.mkdir(parents=True)
    dockerfile.parent.mkdir(parents=True)
    compose.write_text("services:\n  jason-runtime: {}\n")
    dockerfile.write_text(
        "ARG BASE_IMAGE\nFROM " + chr(36) + "{BASE_IMAGE}\n"
    )
    current = root / "opt/jason/current"
    current.parent.mkdir(parents=True, exist_ok=True)
    current.symlink_to(Path("releases") / source_sha)

    manifest = build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-jason-b",
            instance_id="jason-b",
            environment="candidate",
            release_version="0.1.0",
            source_sha=source_sha,
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
                    source_sha=source_sha,
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
                container_runtime="Docker",
                compose="Compose",
            ),
        ),
        generated_at=datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc),
    )
    manifest_path = root / "var/lib/jason/deployment-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
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
    lines = [
        "JASON_SES_DEFAULT_SENDER=test@example.invalid",
        "JASON_OLLAMA_MODEL=qwen-test",
        "JASON_MCP_ENTRA_TENANT_ID=tenant-test",
        "JASON_MCP_ENTRA_CLIENT_ID=client-test",
        "JASON_MCP_RESOURCE_URL=http://127.0.0.1:18000/mcp",
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID=0",
        "JASON_PROVIDER_HEALTH_CANARY_PROVIDERS=autotask,datto_rmm",
    ]
    runtime_config = load_candidate_runtime_config(
        ROOT / "config/candidate-runtime.v1.json",
        ROOT / "config/schemas/candidate-runtime.schema.json",
    )
    for index, item in enumerate(runtime_config["secret_mounts"]):
        source = root / "var/lib/jason/runtime-secrets/test" / str(index)
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("synthetic")
        source.chmod(0o600)
        lines.append(
            str(item["environment_variable"]) + "=" + str(source)
        )
    env.write_text("\n".join(lines) + "\n")
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
    runtime_plan = build_candidate_runtime_plan(
        target_root=root,
        candidate_identity=identity(),
        runtime_config=runtime_config,
        msp_configuration=msp,
        secret_presence_attestation_path=attestation,
        env_file=env,
    )
    mcp_config = load_candidate_mcp_config(
        ROOT / "config/candidate-mcp.v1.json",
        ROOT / "config/schemas/candidate-mcp.schema.json",
    )
    return root, env, runtime_config, runtime_plan, mcp_config


def test_candidate_mcp_plan_uses_candidate_runtime_image_as_base(tmp_path):
    root, env, runtime_config, runtime_plan, mcp_config = prepare(tmp_path)
    plan = build_candidate_mcp_plan(
        target_root=root,
        candidate_identity=identity(),
        runtime_plan=runtime_plan,
        runtime_config=runtime_config,
        mcp_config=mcp_config,
        env_file=env,
    )
    assert plan.base_runtime_image == runtime_plan.image
    assert plan.image == "jason-mcp:candidate-" + ("a" * 12)
    assert plan.container_name == "jason-mcp-candidate"
    assert plan.health_url == "http://127.0.0.1:18000/healthz"
    assert len(plan.secret_mounts) == 4


def test_candidate_mcp_environment_requires_candidate_resource_url(tmp_path):
    _, env, runtime_config, _, mcp_config = prepare(tmp_path)
    env.write_text(
        env.read_text().replace(
            "http://127.0.0.1:18000/mcp",
            "http://127.0.0.1:8000/mcp",
        )
    )
    try:
        validate_candidate_mcp_environment(
            env_file=env,
            runtime_config=runtime_config,
            mcp_config=mcp_config,
        )
    except Exception as exc:
        assert "resource URL" in str(exc)
    else:
        raise AssertionError("candidate MCP resource URL mismatch must fail")


def test_candidate_mcp_build_run_health_and_governance_postcheck(tmp_path):
    root, env, runtime_config, runtime_plan, mcp_config = prepare(tmp_path)
    plan = build_candidate_mcp_plan(
        target_root=root,
        candidate_identity=identity(),
        runtime_plan=runtime_plan,
        runtime_config=runtime_config,
        mcp_config=mcp_config,
        env_file=env,
    )
    calls = []

    def runner(command):
        calls.append(tuple(command))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = execute_candidate_mcp_start(
        plan=plan,
        candidate_identity=identity(),
        runner=runner,
        http_getter=lambda url: (200, {"status": "ok"}),
        health_timeout_seconds=0.1,
        poll_interval_seconds=0,
    )
    assert result["status"] == "mcp_healthy"
    build = next(call for call in calls if call[:2] == ("docker", "build"))
    assert "BASE_IMAGE=" + runtime_plan.image in build
    run = next(call for call in calls if call[:2] == ("docker", "run"))
    assert "127.0.0.1:18000:8000" in run
    assert "--read-only" in run
    assert not any(
        "production-deploy.sh" in " ".join(call)
        for call in calls
    )


def test_candidate_provider_canary_report_is_persisted(tmp_path):
    root, env, runtime_config, runtime_plan, mcp_config = prepare(tmp_path)
    plan = build_candidate_mcp_plan(
        target_root=root,
        candidate_identity=identity(),
        runtime_plan=runtime_plan,
        runtime_config=runtime_config,
        mcp_config=mcp_config,
        env_file=env,
    )
    payload = {
        "schema_version": 1,
        "generated_at": "2026-10-02T22:00:00+00:00",
        "generated_at_epoch": 1790978400.0,
        "principal": "provider-health-canary",
        "policy": "test",
        "results": [
            {
                "provider": "autotask",
                "capability": "service.company.search",
                "healthy": True,
                "latency_seconds": 0.1,
                "error_class": "none",
                "correlation_id": "corr_a",
            },
            {
                "provider": "datto_rmm",
                "capability": "endpoint.device.search",
                "healthy": True,
                "latency_seconds": 0.1,
                "error_class": "none",
                "correlation_id": "corr_b",
            },
        ],
    }

    result = run_candidate_provider_canaries(
        plan=plan,
        target_root=root,
        required_providers=("autotask", "datto_rmm"),
        runner=lambda command: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        ),
    )
    assert result["status"] == "provider_canaries_healthy"
    written = json.loads(
        (root / "var/lib/jason/provider-health-canaries.json").read_text()
    )
    assert len(written["results"]) == 2
