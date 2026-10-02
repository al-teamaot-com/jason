from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from tools.full_recovery_export import (
    CollectedMetadata,
    CollectedPayload,
    FullRecoveryExportError,
    collect_full_recovery_state,
    collection_result_to_members,
    load_collection_spec,
)
from tools.full_recovery_restore import INTERNAL_MANIFEST_MEMBER
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)


ROOT = Path(__file__).resolve().parents[2]


def inventory():
    return json.loads(
        (ROOT / "config/recovery-state-inventory.v1.json").read_text()
    )


def collection():
    return load_collection_spec(
        ROOT / "config/full-recovery-collection.v1.json",
        ROOT / "config/schemas/full-recovery-collection.schema.json",
    )


def make_sqlite(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("create table evidence(value text not null)")
        db.execute("insert into evidence(value) values (?)", (value,))
        db.commit()


def prepare_root(tmp_path: Path):
    root = tmp_path / "candidate"
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
            deployment_id="candidate-recovery-test",
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
            providers=(ProviderIdentity("autotask", False, "bundle"),),
            runtime=RuntimeIdentity(
                os="ubuntu 24.04",
                architecture="x86_64",
                python="3.12.3",
                container_runtime="Docker 29",
                compose="5",
            ),
        ),
        generated_at=datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc),
    )
    manifest_path = root / "var/lib/jason/deployment-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest))

    make_sqlite(root / "var/lib/jason/authority/authority.sqlite3", "authority")
    make_sqlite(root / "var/lib/jason/authority/client-boundaries.sqlite3", "boundaries")
    make_sqlite(root / "var/lib/jason/openclaw/orchestration-events.sqlite3", "events")
    make_sqlite(root / "var/lib/jason/openclaw/approval-continuations.sqlite3", "continuations")
    playbook = root / "var/lib/jason/playbooks/example.json"
    playbook.parent.mkdir(parents=True)
    playbook.write_text('{"run":"synthetic"}')
    return root, manifest


def fake_secret_adapter(source_id, source, root):
    return (
        (
            CollectedPayload(
                state_class="provider-secrets",
                member_name="secrets/provider/example",
                restore_relative_path="var/lib/jason/recovery-secrets/provider/example",
                data=b"synthetic-secret",
                metadata={"adapter": "governed_secret_export"},
            ),
        ),
        (),
    )


def fake_key_adapter(source_id, source, root):
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


def adapters():
    return {
        "governed_secret_export": fake_secret_adapter,
        "governed_key_export": fake_key_adapter,
    }


def test_collection_snapshots_core_state_and_requires_external_secret_adapters(tmp_path):
    root, manifest = prepare_root(tmp_path)
    result = collect_full_recovery_state(
        target_root=root,
        collection_spec=collection(),
        state_inventory=inventory(),
        external_adapters=adapters(),
    )
    assert result.source_deployment_identity_sha256 == manifest["identity_sha256"]
    assert "governed_secret_export" in result.external_adapters_used
    assert "governed_key_export" in result.external_adapters_used

    members = collection_result_to_members(result)
    assert INTERNAL_MANIFEST_MEMBER in members
    assert members["secrets/provider/example"] == b"synthetic-secret"
    assert any(name.startswith("state/playbook-state/") for name in members)

    authority = members["state/identity-authority"]
    snapshot = tmp_path / "snapshot.sqlite3"
    snapshot.write_bytes(authority)
    with sqlite3.connect(snapshot) as db:
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert db.execute("select value from evidence").fetchone()[0] == "authority"


def test_missing_required_adapter_blocks_export(tmp_path):
    root, _ = prepare_root(tmp_path)
    with pytest.raises(
        FullRecoveryExportError,
        match="required recovery adapter unavailable: governed_secret_export",
    ):
        collect_full_recovery_state(
            target_root=root,
            collection_spec=collection(),
            state_inventory=inventory(),
            external_adapters={},
        )


def test_missing_required_core_state_blocks_export(tmp_path):
    root, _ = prepare_root(tmp_path)
    (root / "var/lib/jason/authority/authority.sqlite3").unlink()
    with pytest.raises(
        FullRecoveryExportError,
        match="required recovery source missing: identity-authority",
    ):
        collect_full_recovery_state(
            target_root=root,
            collection_spec=collection(),
            state_inventory=inventory(),
            external_adapters=adapters(),
        )


def test_directory_symlink_is_rejected(tmp_path):
    root, _ = prepare_root(tmp_path)
    (root / "var/lib/jason/playbooks/link").symlink_to(
        root / "etc/jason/msp-policy.json"
    )
    with pytest.raises(
        FullRecoveryExportError,
        match="contains symlink",
    ):
        collect_full_recovery_state(
            target_root=root,
            collection_spec=collection(),
            state_inventory=inventory(),
            external_adapters=adapters(),
        )


def test_live_root_is_refused():
    with pytest.raises(PermissionError, match="live filesystem root"):
        collect_full_recovery_state(
            target_root="/",
            collection_spec=collection(),
            state_inventory=inventory(),
            external_adapters=adapters(),
        )


def test_export_plan_is_secret_safe_and_reports_missing_required_adapters(tmp_path):
    from tools.full_recovery_export import plan_full_recovery_export

    root, manifest = prepare_root(tmp_path)
    plan = plan_full_recovery_export(
        target_root=root,
        collection_spec=collection(),
        state_inventory=inventory(),
        available_adapter_names=(),
    )
    assert plan.status == "blocked"
    assert (
        "required_adapter_unavailable:governed_secret_export"
        in plan.blockers
    )
    assert (
        "required_adapter_unavailable:governed_key_export"
        in plan.blockers
    )
    assert plan.source_deployment_identity_sha256 == manifest["identity_sha256"]

    ready = plan_full_recovery_export(
        target_root=root,
        collection_spec=collection(),
        state_inventory=inventory(),
        available_adapter_names=tuple(adapters()),
    )
    assert ready.status == "ready_for_export"
