from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from bootstrap.candidate_host import CandidateHostIdentity
from bootstrap.candidate_seed_package import (
    inspect_candidate_seed_package,
    stage_candidate_seed_package,
)
from tools.full_recovery_package import create_recovery_package
from tools.full_recovery_restore import assemble_recovery_members


SOURCE_ID = "a" * 64


def identity():
    return CandidateHostIdentity(
        schema_version="1.0",
        environment="candidate",
        instance_id="jason-b",
        bootstrap_authorized=True,
    )


def fixture(tmp_path: Path):
    snapshot = b"synthetic-raft" * 100
    sidecar = (
        hashlib.sha256(snapshot).hexdigest()
        + "  latest.snap\n"
    ).encode()
    init = json.dumps(
        {
            "unseal_keys_b64": ["share-a", "share-b"],
            "unseal_shares": 2,
            "unseal_threshold": 2,
            "root_token": "protected-value",
        }
    ).encode()
    payloads = (
        (
            "provider-secrets",
            "secrets/openbao/raft/latest.snap",
            "var/lib/jason/recovery/openbao/latest.snap",
            snapshot,
            {},
        ),
        (
            "provider-secrets",
            "secrets/openbao/raft/latest.snap.sha256",
            "var/lib/jason/recovery/openbao/latest.snap.sha256",
            sidecar,
            {},
        ),
        (
            "signing-and-recovery-keys",
            "secrets/openbao/init.json",
            "opt/jason/bootstrap/secrets/openbao/init.json",
            init,
            {},
        ),
        (
            "provider-secrets",
            "secrets/openbao/bootstrap/autotask-read-approle/role-id",
            "opt/jason/bootstrap/secrets/openbao/autotask-read-approle/role-id",
            b"role-a\n",
            {},
        ),
        (
            "provider-secrets",
            "secrets/openbao/bootstrap/autotask-read-approle/secret-id",
            "opt/jason/bootstrap/secrets/openbao/autotask-read-approle/secret-id",
            b"credential-a\n",
            {},
        ),
        (
            "provider-secrets",
            "secrets/openbao/bootstrap/datto-rmm-read-approle/role-id",
            "opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/role-id",
            b"role-d\n",
            {},
        ),
        (
            "provider-secrets",
            "secrets/openbao/bootstrap/datto-rmm-read-approle/secret-id",
            "opt/jason/bootstrap/secrets/openbao/datto-rmm-read-approle/secret-id",
            b"credential-d\n",
            {},
        ),
    )
    members = assemble_recovery_members(
        source_deployment_identity_sha256=SOURCE_ID,
        payloads=payloads,
    )
    recipient = X25519PrivateKey.generate()
    signer = Ed25519PrivateKey.generate()
    package = create_recovery_package(
        members=members,
        source_deployment_identity_sha256=SOURCE_ID,
        recipient_public_key=recipient.public_key(),
        recipient_key_id="candidate-seed",
        signer_private_key=signer,
        signer_key_id="candidate-seed-signer",
    )
    package_path = tmp_path / "seed.jrp.json"
    package_path.write_text(json.dumps(package))

    recipient_private = tmp_path / "recipient-private.pem"
    recipient_private.write_bytes(
        recipient.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption(),
        )
    )
    recipient_private.chmod(0o600)

    signer_public = tmp_path / "signer-public.pem"
    signer_public.write_bytes(
        signer.public_key().public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return package_path, recipient_private, signer_public


def test_seed_package_inspection_exposes_paths_not_values(tmp_path):
    package, recipient, signer = fixture(tmp_path)
    inspection = inspect_candidate_seed_package(
        package_path=package,
        recipient_private_key_path=recipient,
        signer_public_key_path=signer,
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    assert inspection.entry_count == 7
    assert (
        "opt/jason/bootstrap/secrets/openbao/autotask-read-approle/secret-id"
        in inspection.restore_relative_paths
    )
    encoded = json.dumps(
        {
            "source": inspection.source_deployment_identity_sha256,
            "paths": inspection.restore_relative_paths,
        }
    )
    assert "credential-a" not in encoded
    assert "protected-value" not in encoded


def test_seed_package_stages_only_encrypted_recovery_entries(tmp_path):
    package, recipient, signer = fixture(tmp_path)
    root = tmp_path / "candidate"
    stage_candidate_seed_package(
        target_root=root,
        candidate_identity=identity(),
        package_path=package,
        recipient_private_key_path=recipient,
        signer_public_key_path=signer,
        expected_source_deployment_identity_sha256=SOURCE_ID,
    )
    role = (
        root
        / "opt/jason/bootstrap/secrets/openbao"
        / "autotask-read-approle/role-id"
    )
    snapshot = root / "var/lib/jason/recovery/openbao/latest.snap"
    assert role.read_bytes() == b"role-a\n"
    assert snapshot.read_bytes().startswith(b"synthetic-raft")
    assert (role.stat().st_mode & 0o777) == 0o600
    assert (snapshot.stat().st_mode & 0o777) == 0o600


def test_seed_source_identity_mismatch_fails_before_writes(tmp_path):
    package, recipient, signer = fixture(tmp_path)
    root = tmp_path / "candidate"
    try:
        stage_candidate_seed_package(
            target_root=root,
            candidate_identity=identity(),
            package_path=package,
            recipient_private_key_path=recipient,
            signer_public_key_path=signer,
            expected_source_deployment_identity_sha256="b" * 64,
        )
    except Exception as exc:
        assert "source deployment identity mismatch" in str(exc)
    else:
        raise AssertionError("wrong seed source identity must fail")
    assert not root.exists()
