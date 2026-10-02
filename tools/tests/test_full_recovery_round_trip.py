from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from tools.full_recovery_export import (
    CollectedPayload,
    load_collection_spec,
)
from tools.full_recovery_export_package import (
    create_encrypted_full_recovery_export,
    write_recovery_package_atomic,
)
from tools.full_recovery_package import decrypt_recovery_package
from tools.full_recovery_restore import (
    acknowledge_reenrollment,
    apply_recovery_restore_plan,
    plan_recovery_restore,
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
NOW = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)


def load(path: str):
    return json.loads((ROOT / path).read_text())


def make_sqlite(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("create table evidence(value text not null)")
        db.execute("insert into evidence(value) values (?)", (value,))
        db.commit()


def prepare_source(tmp_path: Path):
    root = tmp_path / "source"
    for relative, content in {
        "etc/jason/deployment.json": '{"environment":"candidate"}',
        "etc/jason/msp-configuration.json": '{"providers":{}}',
        "etc/jason/msp-policy.json": '{"policy":"synthetic"}',
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    manifest = build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-roundtrip",
            instance_id="jason-a",
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
            providers=(ProviderIdentity("autotask", False, "bundle"),),
            runtime=RuntimeIdentity(
                os="ubuntu 24.04",
                architecture="x86_64",
                python="3.12.3",
                container_runtime="Docker 29",
                compose="5",
            ),
        ),
        generated_at=NOW,
    )
    path = root / "var/lib/jason/deployment-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest))

    make_sqlite(root / "var/lib/jason/authority/authority.sqlite3", "authority")
    make_sqlite(root / "var/lib/jason/authority/client-boundaries.sqlite3", "boundaries")
    make_sqlite(root / "var/lib/jason/openclaw/orchestration-events.sqlite3", "events")
    make_sqlite(root / "var/lib/jason/openclaw/approval-continuations.sqlite3", "continuations")
    return root, manifest


def secret_adapter(source_id, source, root):
    return (
        (
            CollectedPayload(
                state_class="provider-secrets",
                member_name="secrets/provider/api",
                restore_relative_path="var/lib/jason/recovery-secrets/provider/api",
                data=b"synthetic-provider-secret",
                metadata={"adapter": "governed_secret_export"},
            ),
        ),
        (),
    )


def key_adapter(source_id, source, root):
    return (
        (
            CollectedPayload(
                state_class="signing-and-recovery-keys",
                member_name="secrets/keys/signing",
                restore_relative_path="var/lib/jason/recovery-keys/signing",
                data=b"synthetic-signing-key",
                metadata={"adapter": "governed_key_export"},
            ),
        ),
        (),
    )


def test_encrypted_full_recovery_round_trip_to_clean_root(tmp_path):
    source, manifest = prepare_source(tmp_path)
    recovery_private = X25519PrivateKey.generate()
    signer_private = Ed25519PrivateKey.generate()

    package, collection = create_encrypted_full_recovery_export(
        target_root=source,
        collection_spec=load_collection_spec(
            ROOT / "config/full-recovery-collection.v1.json",
            ROOT / "config/schemas/full-recovery-collection.schema.json",
        ),
        state_inventory=load("config/recovery-state-inventory.v1.json"),
        external_adapters={
            "governed_secret_export": secret_adapter,
            "governed_key_export": key_adapter,
        },
        recipient_public_key=recovery_private.public_key(),
        recipient_key_id="owner-recovery-1",
        signer_private_key=signer_private,
        signer_key_id="recovery-signer-1",
        created_at=NOW,
    )
    assert collection.source_deployment_identity_sha256 == manifest["identity_sha256"]

    package_path = write_recovery_package_atomic(
        package,
        output=tmp_path / "jason-a.jrp.json",
    )
    assert (package_path.stat().st_mode & 0o777) == 0o600
    encoded = package_path.read_text()
    assert "synthetic-provider-secret" not in encoded
    assert "synthetic-signing-key" not in encoded

    members = decrypt_recovery_package(
        json.loads(encoded),
        recipient_private_key=recovery_private,
        signer_public_key=signer_private.public_key(),
    )
    target = tmp_path / "restored"
    plan = plan_recovery_restore(
        decrypted_members=members,
        state_inventory=load("config/recovery-state-inventory.v1.json"),
        payload_manifest_schema=load(
            "config/schemas/full-recovery-payload-manifest.schema.json"
        ),
        target_root=target,
        expected_source_deployment_identity_sha256=manifest["identity_sha256"],
    )
    assert plan.status == "blocked_for_reenrollment"
    # Full export records machine identity as metadata requiring explicit re-enrollment.
    assert "reenrollment_required:host-bound-identity" in plan.blockers

    plan = acknowledge_reenrollment(
        plan=plan,
        completed_state_classes=("host-bound-identity",),
    )
    assert plan.status == "ready_for_restore"
    result = apply_recovery_restore_plan(
        plan=plan,
        decrypted_members=members,
    )
    assert result["status"] == "restore_payload_applied"
    assert (
        target / "var/lib/jason/recovery-secrets/provider/api"
    ).read_bytes() == b"synthetic-provider-secret"

    with sqlite3.connect(
        target / "var/lib/jason/authority/authority.sqlite3"
    ) as db:
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert db.execute("select value from evidence").fetchone()[0] == "authority"
