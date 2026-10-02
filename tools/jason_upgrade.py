from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.reproducible_upgrade import (
    MigrationStep,
    UpgradePlan,
    load_migration_catalog,
    plan_rollback,
    plan_upgrade,
)


def _load(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_checkpoint(receipt, schema):
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(receipt),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        raise ValueError("upgrade checkpoint receipt invalid: " + errors[0].message)


def _upgrade_plan_from_dict(payload):
    return UpgradePlan(
        schema_version=str(payload["schema_version"]),
        current_deployment_identity_sha256=str(
            payload["current_deployment_identity_sha256"]
        ),
        target_deployment_identity_sha256=str(
            payload["target_deployment_identity_sha256"]
        ),
        instance_id=str(payload["instance_id"]),
        environment=str(payload["environment"]),
        current_source_sha=str(payload["current_source_sha"]),
        target_source_sha=str(payload["target_source_sha"]),
        current_artifact_digest=str(payload["current_artifact_digest"]),
        target_artifact_digest=str(payload["target_artifact_digest"]),
        checkpoint_recovery_package_sha256=payload.get(
            "checkpoint_recovery_package_sha256"
        ),
        configuration_changes=tuple(payload.get("configuration_changes", ())),
        provider_changes=tuple(payload.get("provider_changes", ())),
        migrations=tuple(
            MigrationStep(
                migration_id=str(item["migration_id"]),
                store=str(item["store"]),
                from_version=str(item["from_version"]),
                to_version=str(item["to_version"]),
                reversible=bool(item["reversible"]),
                rollback_strategy=str(item["rollback_strategy"]),
            )
            for item in payload.get("migrations", ())
        ),
        rollback_mode=str(payload["rollback_mode"]),
        automatic_rollback_safe=bool(payload["automatic_rollback_safe"]),
        blockers=tuple(payload.get("blockers", ())),
        status=str(payload["status"]),
        plan_sha256=str(payload["plan_sha256"]),
    )


def command_plan(args):
    current = _load(args.current_manifest)
    target = _load(args.target_manifest)
    checkpoint = _load(args.checkpoint_receipt)
    checkpoint_schema = _load(args.checkpoint_schema)
    _validate_checkpoint(checkpoint, checkpoint_schema)
    catalog = load_migration_catalog(
        args.migration_catalog,
        args.migration_schema,
    )
    plan = plan_upgrade(
        current_manifest=current,
        target_manifest=target,
        migration_catalog=catalog,
        checkpoint_receipt=checkpoint,
    )
    print(json.dumps(asdict(plan), indent=2, sort_keys=True))
    return 0 if plan.status == "ready_for_upgrade" else 3


def command_rollback_plan(args):
    plan = _upgrade_plan_from_dict(_load(args.upgrade_plan))
    rollback = plan_rollback(plan)
    print(json.dumps(asdict(rollback), indent=2, sort_keys=True))
    return 0 if rollback.status == "ready_for_rollback" else 3


def build_parser():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Plan Jason candidate upgrades and deterministic rollback"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--current-manifest", required=True)
    plan.add_argument("--target-manifest", required=True)
    plan.add_argument("--checkpoint-receipt", required=True)
    plan.add_argument(
        "--checkpoint-schema",
        default=str(repo / "config/schemas/upgrade-checkpoint-receipt.schema.json"),
    )
    plan.add_argument(
        "--migration-catalog",
        default=str(repo / "config/upgrade-migrations.v1.json"),
    )
    plan.add_argument(
        "--migration-schema",
        default=str(repo / "config/schemas/upgrade-migration-catalog.schema.json"),
    )
    plan.set_defaults(func=command_plan)

    rollback = sub.add_parser("rollback-plan")
    rollback.add_argument("--upgrade-plan", required=True)
    rollback.set_defaults(func=command_rollback_plan)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, sort_keys=True))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
