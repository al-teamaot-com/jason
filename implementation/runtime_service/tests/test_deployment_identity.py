from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from jason_runtime.deployment_identity import (
    DeploymentManifestError,
    FileDeploymentManifestProvider,
)
from jason_runtime.http import RuntimeHttpApplication
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)


class Ingress:
    def handle(self, envelope):
        raise AssertionError("deployment identity endpoint must not invoke conversation ingress")


def build_manifest():
    return build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-a",
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
            ),
            schemas=(SchemaIdentity("authority", "1"),),
            providers=(ProviderIdentity("autotask", True, "ticketing-v1"),),
            runtime=RuntimeIdentity(
                os="Ubuntu 24.04",
                architecture="x86_64",
                python="3.12.3",
                container_runtime="Docker 29.6.2",
                compose="5.3.1",
            ),
        ),
        generated_at=datetime(2026, 10, 2, 17, 0, tzinfo=timezone.utc),
    )


def test_runtime_manifest_endpoint_returns_authoritative_identity(tmp_path):
    path = tmp_path / "deployment-manifest.json"
    manifest = build_manifest()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    app = RuntimeHttpApplication(
        Ingress(),
        deployment_manifest_provider=FileDeploymentManifestProvider(path),
    )

    response = app.dispatch(
        method="GET",
        path="/v1/system/deployment-manifest",
        headers={},
        body=b"",
    )
    assert response.status_code == 200
    assert response.body["identity_sha256"] == manifest["identity_sha256"]
    assert response.body["platform"]["source_sha"] == "a" * 40


def test_health_surfaces_manifest_identity_without_full_manifest(tmp_path):
    path = tmp_path / "deployment-manifest.json"
    manifest = build_manifest()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    app = RuntimeHttpApplication(
        Ingress(),
        deployment_manifest_provider=FileDeploymentManifestProvider(path),
    )

    response = app.dispatch(method="GET", path="/healthz", headers={}, body=b"")
    assert response.status_code == 200
    assert response.body["deployment_manifest"] == "available"
    assert response.body["deployment_identity_sha256"] == manifest["identity_sha256"]
    assert "platform" not in response.body


def test_manifest_tamper_fails_closed(tmp_path):
    path = tmp_path / "deployment-manifest.json"
    manifest = build_manifest()
    manifest["platform"]["source_sha"] = "9" * 40
    path.write_text(json.dumps(manifest), encoding="utf-8")
    provider = FileDeploymentManifestProvider(path)

    with pytest.raises(DeploymentManifestError, match="hash mismatch"):
        provider.read()

    response = RuntimeHttpApplication(
        Ingress(),
        deployment_manifest_provider=provider,
    ).dispatch(
        method="GET",
        path="/v1/system/deployment-manifest",
        headers={},
        body=b"",
    )
    assert response.status_code == 503
    assert response.body["error_code"] == "deployment_manifest_invalid"


def test_manifest_endpoint_is_unavailable_when_not_configured():
    response = RuntimeHttpApplication(Ingress()).dispatch(
        method="GET",
        path="/v1/system/deployment-manifest",
        headers={},
        body=b"",
    )
    assert response.status_code == 503
    assert response.body["error_code"] == "deployment_manifest_not_configured"
