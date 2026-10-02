from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)
from tools.reproducible_upgrade import (
    execute_candidate_upgrade,
    plan_upgrade,
)


NOW = datetime(2026, 10, 2, 23, 0, tzinfo=timezone.utc)


def manifest(source: str, artifact: str, schema: str):
    return build_deployment_manifest(
        DeploymentManifestInputs(
            deployment_id="candidate-" + source[:8],
            instance_id="jason-b",
            environment="candidate",
            release_version="0.1.0",
            source_sha=source,
            artifact_digest=artifact,
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
                    source_sha=source,
                    artifact_digest=artifact,
                ),
            ),
            schemas=(SchemaIdentity("authority", schema),),
            providers=(ProviderIdentity("autotask", True, "bundle"),),
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


def root_layout(tmp_path: Path, current, target):
    root = tmp_path / "candidate"
    current_release = root / "opt/jason/releases" / current["platform"]["source_sha"]
    target_release = root / "opt/jason/releases" / target["platform"]["source_sha"]
    current_release.mkdir(parents=True)
    target_release.mkdir(parents=True)
    current_link = root / "opt/jason/current"
    current_link.symlink_to(
        Path("releases") / current["platform"]["source_sha"]
    )
    manifest_path = root / "var/lib/jason/deployment-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(current))
    return root


def test_code_only_upgrade_switches_release_and_manifest(tmp_path):
    current = manifest("a" * 40, "sha256:" + "1" * 64, "schema-a")
    target = manifest("b" * 40, "sha256:" + "2" * 64, "schema-a")
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog={"schema_version": "1.0", "migrations": []},
        checkpoint_receipt=checkpoint(current),
    )
    root = root_layout(tmp_path, current, target)
    result = execute_candidate_upgrade(
        target_root=root,
        plan=plan,
        current_manifest=current,
        target_manifest=target,
        migration_apply=lambda step, root: None,
        migration_reverse=lambda step, root: None,
        verify_target=lambda target, root: True,
    )
    assert result["status"] == "upgraded"
    assert (root / "opt/jason/current").resolve() == (
        root / "opt/jason/releases" / ("b" * 40)
    )
    written = json.loads(
        (root / "var/lib/jason/deployment-manifest.json").read_text()
    )
    assert written["identity_sha256"] == target["identity_sha256"]


def test_failed_code_only_verification_rolls_back_atomically(tmp_path):
    current = manifest("a" * 40, "sha256:" + "1" * 64, "schema-a")
    target = manifest("b" * 40, "sha256:" + "2" * 64, "schema-a")
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog={"schema_version": "1.0", "migrations": []},
        checkpoint_receipt=checkpoint(current),
    )
    root = root_layout(tmp_path, current, target)
    result = execute_candidate_upgrade(
        target_root=root,
        plan=plan,
        current_manifest=current,
        target_manifest=target,
        migration_apply=lambda step, root: None,
        migration_reverse=lambda step, root: None,
        verify_target=lambda target, root: False,
    )
    assert result["status"] == "rolled_back"
    assert (root / "opt/jason/current").resolve() == (
        root / "opt/jason/releases" / ("a" * 40)
    )
    written = json.loads(
        (root / "var/lib/jason/deployment-manifest.json").read_text()
    )
    assert written["identity_sha256"] == current["identity_sha256"]


def test_reversible_migration_is_reversed_on_verification_failure(tmp_path):
    current = manifest("a" * 40, "sha256:" + "1" * 64, "schema-a")
    target = manifest("b" * 40, "sha256:" + "2" * 64, "schema-b")
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
        migration_catalog={"schema_version": "1.0", "migrations": [edge]},
        checkpoint_receipt=checkpoint(current),
    )
    root = root_layout(tmp_path, current, target)
    events = []
    result = execute_candidate_upgrade(
        target_root=root,
        plan=plan,
        current_manifest=current,
        target_manifest=target,
        migration_apply=lambda step, root: events.append(("apply", step.migration_id)),
        migration_reverse=lambda step, root: events.append(("reverse", step.migration_id)),
        verify_target=lambda target, root: False,
    )
    assert result["status"] == "rolled_back"
    assert events == [
        ("apply", "authority-a-b"),
        ("reverse", "authority-a-b"),
    ]


def test_irreversible_migration_requires_explicit_checkpoint_restore(tmp_path):
    current = manifest("a" * 40, "sha256:" + "1" * 64, "schema-a")
    target = manifest("b" * 40, "sha256:" + "2" * 64, "schema-b")
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
        migration_catalog={"schema_version": "1.0", "migrations": [edge]},
        checkpoint_receipt=checkpoint(current),
    )
    root = root_layout(tmp_path, current, target)
    result = execute_candidate_upgrade(
        target_root=root,
        plan=plan,
        current_manifest=current,
        target_manifest=target,
        migration_apply=lambda step, root: None,
        migration_reverse=lambda step, root: None,
        verify_target=lambda target, root: False,
    )
    assert result["status"] == "checkpoint_restore_required"
    assert result["automatic_rollback_performed"] is False

    restored = []
    root = root_layout(tmp_path / "authorized", current, target)
    result = execute_candidate_upgrade(
        target_root=root,
        plan=plan,
        current_manifest=current,
        target_manifest=target,
        migration_apply=lambda step, root: None,
        migration_reverse=lambda step, root: None,
        verify_target=lambda target, root: False,
        checkpoint_restore=lambda digest, root: restored.append(digest),
        authorize_checkpoint_restore=True,
    )
    assert result["status"] == "rolled_back"
    assert restored == ["9" * 64]


def test_live_root_and_missing_target_release_fail_before_mutation(tmp_path):
    current = manifest("a" * 40, "sha256:" + "1" * 64, "schema-a")
    target = manifest("b" * 40, "sha256:" + "2" * 64, "schema-a")
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog={"schema_version": "1.0", "migrations": []},
        checkpoint_receipt=checkpoint(current),
    )
    try:
        execute_candidate_upgrade(
            target_root="/",
            plan=plan,
            current_manifest=current,
            target_manifest=target,
            migration_apply=lambda step, root: None,
            migration_reverse=lambda step, root: None,
            verify_target=lambda target, root: True,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("live root must be refused")

    root = root_layout(tmp_path, current, target)
    target_release = root / "opt/jason/releases" / ("b" * 40)
    target_release.rmdir()
    try:
        execute_candidate_upgrade(
            target_root=root,
            plan=plan,
            current_manifest=current,
            target_manifest=target,
            migration_apply=lambda step, root: None,
            migration_reverse=lambda step, root: None,
            verify_target=lambda target, root: True,
        )
    except Exception as exc:
        assert "target release is not staged" in str(exc)
    else:
        raise AssertionError("missing target release must fail")
