from __future__ import annotations

from datetime import datetime, timezone
import json

from jsonschema import Draft202012Validator

from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
    canonical_json_file_sha256,
    deployment_identity_sha256,
    render_deployment_manifest,
)


NOW = datetime(2026, 10, 2, 14, 30, tzinfo=timezone.utc)


def inputs():
    return DeploymentManifestInputs(
        deployment_id="deployment-a",
        instance_id="jason-b",
        environment="candidate",
        release_version="1.0.0-rc1",
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
                release_version="1.0.0-rc1",
                source_sha="a" * 40,
                artifact_digest="sha256:" + "b" * 64,
            ),
            ComponentIdentity(
                name="observability",
                kind="supporting",
                required=True,
                release_version="obs-4",
                source_sha="1" * 40,
                artifact_digest="sha256:" + "2" * 64,
            ),
        ),
        schemas=(SchemaIdentity("authority", "4"), SchemaIdentity("orchestration", "7")),
        providers=(
            ProviderIdentity("autotask", True, "ticketing-v1"),
            ProviderIdentity("datto_rmm", True, "endpoint-v1"),
        ),
        runtime=RuntimeIdentity(
            os="Ubuntu 24.04",
            architecture="x86_64",
            python="3.12.3",
            container_runtime="Docker 29.6.2",
            compose="5.3.1",
        ),
    )


def test_manifest_is_component_aware_and_schema_valid():
    manifest = build_deployment_manifest(inputs(), generated_at=NOW)
    schema = json.loads(
        open("config/schemas/deployment-manifest.schema.json", encoding="utf-8").read()
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest)
    assert manifest["components"][0]["name"] == "core"
    assert manifest["components"][1]["name"] == "observability"
    assert manifest["components"][0]["source_sha"] != manifest["components"][1]["source_sha"]


def test_identity_digest_is_stable_across_generation_time():
    first = build_deployment_manifest(inputs(), generated_at=NOW)
    later = build_deployment_manifest(
        inputs(),
        generated_at=datetime(2026, 10, 2, 15, 30, tzinfo=timezone.utc),
    )
    assert first["generated_at"] != later["generated_at"]
    assert first["identity_sha256"] == later["identity_sha256"]
    assert deployment_identity_sha256(first) == first["identity_sha256"]


def test_configuration_revision_comes_from_canonical_json_content(tmp_path):
    path = tmp_path / "msp.json"
    path.write_text('{"b":2,"a":1}\n', encoding="utf-8")
    first = canonical_json_file_sha256(path)
    path.write_text('{\n  "a": 1,\n  "b": 2\n}\n', encoding="utf-8")
    second = canonical_json_file_sha256(path)
    assert first == second
    path.write_text('{"a":1,"b":3}\n', encoding="utf-8")
    assert canonical_json_file_sha256(path) != first


def test_human_render_contains_authoritative_identity():
    manifest = build_deployment_manifest(inputs(), generated_at=NOW)
    rendered = render_deployment_manifest(manifest)
    assert "1.0.0-rc1" in rendered
    assert "Source SHA: " + "a" * 40 in rendered
    assert "observability" in rendered
    assert manifest["identity_sha256"] in rendered
