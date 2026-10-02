from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)
from tools.reproducible_upgrade import plan_rollback, plan_upgrade


NOW = datetime(2026, 10, 2, 22, 0, tzinfo=timezone.utc)


def manifest(
    *,
    source: str,
    artifact: str,
    schema: str = "schema-a",
    config: str = "c" * 64,
    policy: str = "d" * 64,
    provider_enabled: bool = True,
    instance: str = "jason-b",
):
    return build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-" + source[:8],
            instance_id=instance,
            environment="candidate",
            release_version="0.1.0",
            source_sha=source,
            artifact_digest=artifact,
            deployment_revision="e" * 64,
            msp_configuration_revision=config,
            msp_policy_revision=policy,
            playbook_revision="f" * 64,
            components=(
                ComponentIdentity(
                    name="core",
                    kind="runtime",
                    required=True,
                    release_version="0.1.0",
                    source_sha=source,
                    artifact_digest=artifact,
                ),
            ),
            schemas=(SchemaIdentity("authority", schema),),
            providers=(
                ProviderIdentity("autotask", provider_enabled, "bundle"),
            ),
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


def checkpoint(current):
    return {
        "schema_version": "1.0",
        "source_deployment_identity_sha256": current["identity_sha256"],
        "recovery_package_sha256": "9" * 64,
        "verified": True,
        "restorable": True,
    }


def catalog(*items):
    return {"schema_version": "1.0", "migrations": list(items)}


def test_code_only_upgrade_is_ready_and_automatically_rollback_safe():
    current = manifest(source="a" * 40, artifact="sha256:" + "1" * 64)
    target = manifest(source="b" * 40, artifact="sha256:" + "2" * 64)
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(),
        checkpoint_receipt=checkpoint(current),
    )
    assert plan.status == "ready_for_upgrade"
    assert plan.rollback_mode == "code_only"
    assert plan.automatic_rollback_safe is True
    rollback = plan_rollback(plan)
    assert rollback.status == "ready_for_rollback"
    assert rollback.automatic is True


def test_every_upgrade_requires_verified_checkpoint():
    current = manifest(source="a" * 40, artifact="sha256:" + "1" * 64)
    target = manifest(source="b" * 40, artifact="sha256:" + "2" * 64)
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(),
        checkpoint_receipt=None,
    )
    assert plan.status == "blocked"
    assert "pre_upgrade_checkpoint_missing" in plan.blockers


def test_checkpoint_must_bind_exact_current_deployment_identity():
    current = manifest(source="a" * 40, artifact="sha256:" + "1" * 64)
    target = manifest(source="b" * 40, artifact="sha256:" + "2" * 64)
    receipt = checkpoint(current)
    receipt["source_deployment_identity_sha256"] = "0" * 64
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(),
        checkpoint_receipt=receipt,
    )
    assert "checkpoint_identity_mismatch" in plan.blockers


def test_schema_change_without_exact_migration_edge_is_blocked():
    current = manifest(
        source="a" * 40,
        artifact="sha256:" + "1" * 64,
        schema="schema-a",
    )
    target = manifest(
        source="b" * 40,
        artifact="sha256:" + "2" * 64,
        schema="schema-b",
    )
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(),
        checkpoint_receipt=checkpoint(current),
    )
    assert plan.status == "blocked"
    assert (
        "migration_edge_missing:authority:schema-a->schema-b"
        in plan.blockers
    )


def test_reversible_schema_migration_has_deterministic_reverse_order():
    current = manifest(
        source="a" * 40,
        artifact="sha256:" + "1" * 64,
        schema="schema-a",
    )
    target = manifest(
        source="b" * 40,
        artifact="sha256:" + "2" * 64,
        schema="schema-b",
    )
    edge = {
        "id": "authority-a-b",
        "store": "authority",
        "from_version": "schema-a",
        "to_version": "schema-b",
        "reversible": True,
        "rollback_strategy": "reverse_migration",
    }
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(edge),
        checkpoint_receipt=checkpoint(current),
    )
    assert plan.status == "ready_for_upgrade"
    assert plan.rollback_mode == "reverse_migrations_then_restore_configuration"
    assert plan.automatic_rollback_safe is True
    rollback = plan_rollback(plan)
    assert rollback.reverse_migrations == ("authority-a-b",)
    assert rollback.automatic is True


def test_irreversible_schema_migration_requires_checkpoint_restore():
    current = manifest(
        source="a" * 40,
        artifact="sha256:" + "1" * 64,
        schema="schema-a",
    )
    target = manifest(
        source="b" * 40,
        artifact="sha256:" + "2" * 64,
        schema="schema-b",
    )
    edge = {
        "id": "authority-a-b",
        "store": "authority",
        "from_version": "schema-a",
        "to_version": "schema-b",
        "reversible": False,
        "rollback_strategy": "restore_checkpoint",
    }
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(edge),
        checkpoint_receipt=checkpoint(current),
    )
    assert plan.status == "ready_for_upgrade"
    assert plan.rollback_mode == "restore_checkpoint"
    assert plan.automatic_rollback_safe is False
    rollback = plan_rollback(plan)
    assert rollback.status == "ready_for_rollback"
    assert rollback.automatic is False
    assert rollback.recovery_package_sha256 == "9" * 64


def test_configuration_and_provider_changes_force_state_aware_rollback():
    current = manifest(
        source="a" * 40,
        artifact="sha256:" + "1" * 64,
        config="c" * 64,
        provider_enabled=True,
    )
    target = manifest(
        source="b" * 40,
        artifact="sha256:" + "2" * 64,
        config="1" * 64,
        provider_enabled=False,
    )
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(),
        checkpoint_receipt=checkpoint(current),
    )
    assert "msp_configuration_revision" in plan.configuration_changes
    assert plan.provider_changes == ("autotask",)
    assert plan.rollback_mode == "restore_checkpoint"
    assert plan.automatic_rollback_safe is False


def test_instance_change_is_blocked():
    current = manifest(source="a" * 40, artifact="sha256:" + "1" * 64)
    target = manifest(
        source="b" * 40,
        artifact="sha256:" + "2" * 64,
        instance="different-instance",
    )
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog(),
        checkpoint_receipt=checkpoint(current),
    )
    assert "instance_identity_mismatch" in plan.blockers
