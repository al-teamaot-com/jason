from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import tarfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from bootstrap.clean_install import HostObservation
from tools.zero_to_operational_host_plan import (
    preflight_host_acceptance_plan,
)


ROOT = Path(__file__).resolve().parents[2]


def host():
    return HostObservation(
        os_id="ubuntu",
        os_version="24.04",
        architecture="x86_64",
        python_version="3.12.3",
        docker_version="Docker version 29",
        compose_version="Docker Compose version 5",
    )


def release(tmp_path: Path, name: str, marker: bytes):
    path = tmp_path / f"{name}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo("release.txt")
        info.size = len(marker)
        archive.addfile(info, io.BytesIO(marker))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def plan_fixture(tmp_path: Path):
    identity = tmp_path / "candidate-host.json"
    identity.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "environment": "candidate",
                "instance_id": "jason-b",
                "bootstrap_authorized": True,
            }
        )
    )
    identity.chmod(0o640)

    config = tmp_path / "msp-config.json"
    config.write_text(
        (ROOT / "config/examples/msp-configuration.example.json").read_text()
    )
    policy = tmp_path / "msp-policy.json"
    policy.write_text(
        (ROOT / "config/examples/msp-policy.example.json").read_text()
    )

    runtime_env = tmp_path / "candidate-runtime.env"
    candidate_root = tmp_path / "blank"
    openbao_root = (
        candidate_root / "opt/jason/bootstrap/secrets/openbao"
    )
    runtime_lines = [
        "JASON_SES_DEFAULT_SENDER=test@example.invalid",
        "JASON_OLLAMA_MODEL=qwen-test",
        "JASON_MCP_ENTRA_TENANT_ID=tenant-test",
        "JASON_MCP_ENTRA_CLIENT_ID=client-test",
        "JASON_MCP_RESOURCE_URL=http://127.0.0.1:18000/mcp",
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID=0",
        "JASON_PROVIDER_HEALTH_CANARY_PROVIDERS=autotask,datto_rmm",
        "JASON_OPENBAO_ROLE_ID_HOST_PATH="
        + str(openbao_root / "datto-rmm-read-approle/role-id"),
        "JASON_OPENBAO_SECRET_ID_HOST_PATH="
        + str(openbao_root / "datto-rmm-read-approle/secret-id"),
        "JASON_AUTOTASK_OPENBAO_ROLE_ID_HOST_PATH="
        + str(openbao_root / "autotask-read-approle/role-id"),
        "JASON_AUTOTASK_OPENBAO_SECRET_ID_HOST_PATH="
        + str(openbao_root / "autotask-read-approle/secret-id"),
    ]
    runtime_env.write_text("\n".join(runtime_lines) + "\n")
    runtime_env.chmod(0o640)

    attestation = tmp_path / "secret-attestation.json"
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

    openbao_snapshot = tmp_path / "openbao-source.snap"
    openbao_snapshot.write_bytes(b"synthetic-openbao-snapshot" * 30)
    openbao_snapshot.chmod(0o600)
    openbao_checksum = tmp_path / "openbao-source.snap.sha256"
    openbao_checksum.write_text(
        hashlib.sha256(openbao_snapshot.read_bytes()).hexdigest()
        + "  openbao-source.snap\n"
    )
    openbao_checksum.chmod(0o600)
    openbao_init = tmp_path / "openbao-init.json"
    openbao_init.write_text(
        json.dumps(
            {
                "unseal_keys_b64": ["share-a", "share-b", "share-c"],
                "unseal_threshold": 2,
                "root_token": "synthetic-root-token",
            }
        )
    )
    openbao_init.chmod(0o600)

    recovery = X25519PrivateKey.generate()
    public = tmp_path / "recovery-public.pem"
    public.write_bytes(
        recovery.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        )
    )
    signer = Ed25519PrivateKey.generate()
    signer_private = tmp_path / "signer-private.pem"
    signer_private.write_bytes(
        signer.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
    )
    signer_private.chmod(0o600)

    current, current_digest = release(tmp_path, "current", b"release-a")
    nxt, next_digest = release(tmp_path, "next", b"release-b")
    payload = {
        "schema_version": "1.0",
        "scenario_id": "jason-v1-host-acceptance",
        "candidate_host_identity": str(identity),
        "current_release": {
            "archive": str(current),
            "sha256": current_digest,
            "source_sha": "a" * 40,
        },
        "next_release": {
            "archive": str(nxt),
            "sha256": next_digest,
            "source_sha": "b" * 40,
        },
        "msp_configuration": str(config),
        "msp_policy": str(policy),
        "secret_presence_attestation": str(attestation),
        "candidate_runtime_env": str(runtime_env),
        "openbao_recovery": {
            "snapshot": str(openbao_snapshot),
            "checksum": str(openbao_checksum),
            "init_file": str(openbao_init),
        },
        "recovery_recipient_public_key": str(public),
        "recovery_signer_private_key": str(signer_private),
        "provider_canary": {
            "container": "jason-mcp-pilot",
            "required_providers": ["autotask", "datto_rmm"],
        },
        "governed_workflow": {
            "capability": "service.company.search",
            "organization_id": "0",
            "mutation_expected": False,
        },
        "second_clean_environment_required": True,
        "production_authorized": False,
    }
    plan = tmp_path / "host-plan.json"
    plan.write_text(json.dumps(payload))
    return plan, payload


def test_complete_blank_host_plan_is_ready(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, _ = plan_fixture(tmp_path)
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert result.status == "ready_for_host_acceptance"
    assert result.clean_host is True
    assert result.enabled_providers == ("autotask", "datto_rmm")
    assert result.required_secret_references == (
        "autotask.readonly",
        "datto_rmm.readonly",
    )
    assert result.recovery_keys_valid is True
    assert result.openbao_recovery_valid is True
    assert result.runtime_environment_valid is True
    assert result.mcp_environment_valid is True
    assert result.ollama_model == "qwen-test"
    assert result.production_authorized is False


def test_provider_canary_set_must_match_enabled_providers(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, payload = plan_fixture(tmp_path)
    payload["provider_canary"]["required_providers"] = ["autotask"]
    plan.write_text(json.dumps(payload))
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert result.status == "blocked"
    assert any(
        item.startswith("provider_canary_set_mismatch:")
        for item in result.blockers
    )


def test_missing_secret_reference_blocks_host_acceptance(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, payload = plan_fixture(tmp_path)
    attestation = Path(payload["secret_presence_attestation"])
    attestation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contains_secret_values": False,
                "available_references": ["autotask.readonly"],
            }
        )
    )
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert "secret_reference_missing:datto_rmm.readonly" in result.blockers


def test_release_digest_tampering_blocks_before_host_acceptance(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, payload = plan_fixture(tmp_path)
    Path(payload["current_release"]["archive"]).write_bytes(b"tampered")
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert any(
        item.startswith("current_release:current release artifact SHA-256 mismatch")
        for item in result.blockers
    )


def test_signer_private_key_permissions_must_be_private(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, payload = plan_fixture(tmp_path)
    Path(payload["recovery_signer_private_key"]).chmod(0o644)
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert any(
        item.startswith("recovery_keys:")
        and "permissions are too broad" in item
        for item in result.blockers
    )


def test_noncanonical_runtime_credential_path_blocks_host_preflight(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, payload = plan_fixture(tmp_path)
    env = Path(payload["candidate_runtime_env"])
    lines = env.read_text().splitlines()
    index = next(
        i for i, line in enumerate(lines)
        if line.startswith("JASON_OPENBAO_ROLE_ID_HOST_PATH=")
    )
    lines[index] = (
        "JASON_OPENBAO_ROLE_ID_HOST_PATH="
        + str(tmp_path / "other-role-id")
    )
    env.write_text("\n".join(lines) + "\n")
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert result.status == "blocked"
    assert any(
        item.startswith("candidate_runtime_env:")
        and "canonical OpenBao restore outputs" in item
        for item in result.blockers
    )


def test_wrong_mcp_resource_url_blocks_host_preflight(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, payload = plan_fixture(tmp_path)
    env = Path(payload["candidate_runtime_env"])
    env.write_text(
        env.read_text().replace(
            "http://127.0.0.1:18000/mcp",
            "http://127.0.0.1:8000/mcp",
        )
    )
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert result.status == "blocked"
    assert any(
        item.startswith("candidate_mcp_env:")
        and "resource URL" in item
        for item in result.blockers
    )

def test_openbao_snapshot_tampering_blocks_host_preflight(tmp_path):
    blank = tmp_path / "blank"
    blank.mkdir()
    plan, payload = plan_fixture(tmp_path)
    Path(payload["openbao_recovery"]["snapshot"]).write_bytes(b"tampered")
    result = preflight_host_acceptance_plan(
        plan_path=plan,
        repository_root=ROOT,
        target_root=blank,
        host=host(),
        effective_uid=0,
    )
    assert result.status == "blocked"
    assert any(
        item.startswith("openbao_recovery:")
        and "checksum verification failed" in item
        for item in result.blockers
    )
