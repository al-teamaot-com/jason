from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from tools import jason_upgrade
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
)


NOW = datetime(2026, 10, 2, 23, 0, tzinfo=timezone.utc)


def manifest(source, artifact):
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
            schemas=(SchemaIdentity("authority", "schema-a"),),
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


def write(path, value):
    path.write_text(json.dumps(value))
    return path


def test_upgrade_cli_plan_and_rollback_plan(tmp_path, capsys):
    current = manifest("a" * 40, "sha256:" + "1" * 64)
    target = manifest("b" * 40, "sha256:" + "2" * 64)
    current_path = write(tmp_path / "current.json", current)
    target_path = write(tmp_path / "target.json", target)
    checkpoint = write(
        tmp_path / "checkpoint.json",
        {
            "schema_version": "1.0",
            "source_deployment_identity_sha256": current["identity_sha256"],
            "recovery_package_sha256": "9" * 64,
            "verified": True,
            "restorable": True,
        },
    )

    args = jason_upgrade.build_parser().parse_args(
        [
            "plan",
            "--current-manifest",
            str(current_path),
            "--target-manifest",
            str(target_path),
            "--checkpoint-receipt",
            str(checkpoint),
        ]
    )
    assert jason_upgrade.command_plan(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "ready_for_upgrade"
    assert plan["rollback_mode"] == "code_only"

    plan_path = write(tmp_path / "upgrade-plan.json", plan)
    args = jason_upgrade.build_parser().parse_args(
        ["rollback-plan", "--upgrade-plan", str(plan_path)]
    )
    assert jason_upgrade.command_rollback_plan(args) == 0
    rollback = json.loads(capsys.readouterr().out)
    assert rollback["status"] == "ready_for_rollback"
    assert rollback["automatic"] is True


def test_upgrade_cli_checkpoint_schema_blocks_unverified_receipt(tmp_path):
    current = manifest("a" * 40, "sha256:" + "1" * 64)
    target = manifest("b" * 40, "sha256:" + "2" * 64)
    checkpoint = {
        "schema_version": "1.0",
        "source_deployment_identity_sha256": current["identity_sha256"],
        "recovery_package_sha256": "9" * 64,
        "verified": False,
        "restorable": True,
    }
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "config/schemas/upgrade-checkpoint-receipt.schema.json"
        ).read_text()
    )
    try:
        jason_upgrade._validate_checkpoint(checkpoint, schema)
    except ValueError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("unverified checkpoint must be rejected")
