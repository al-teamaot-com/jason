from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
)

from jason_runtime.deployment_identity import validate_deployment_manifest


class UpgradePlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MigrationStep:
    migration_id: str
    store: str
    from_version: str
    to_version: str
    reversible: bool
    rollback_strategy: str


@dataclass(frozen=True, slots=True)
class UpgradePlan:
    schema_version: str
    current_deployment_identity_sha256: str
    target_deployment_identity_sha256: str
    instance_id: str
    environment: str
    current_source_sha: str
    target_source_sha: str
    current_artifact_digest: str
    target_artifact_digest: str
    checkpoint_recovery_package_sha256: str | None
    configuration_changes: tuple[str, ...]
    provider_changes: tuple[str, ...]
    migrations: tuple[MigrationStep, ...]
    rollback_mode: str
    automatic_rollback_safe: bool
    blockers: tuple[str, ...]
    status: str
    plan_sha256: str


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    schema_version: str
    upgrade_plan_sha256: str
    mode: str
    current_deployment_identity_sha256: str
    failed_target_deployment_identity_sha256: str
    reverse_migrations: tuple[str, ...]
    recovery_package_sha256: str | None
    automatic: bool
    blockers: tuple[str, ...]
    status: str


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_migration_catalog(
    document_path: str | Path,
    schema_path: str | Path,
) -> dict[str, Any]:
    document = json.loads(Path(document_path).read_text(encoding="utf-8"))
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        raise UpgradePlanError(
            "upgrade migration catalog invalid: " + errors[0].message
        )
    ids = [str(item["id"]) for item in document["migrations"]]
    if len(ids) != len(set(ids)):
        raise UpgradePlanError("upgrade migration IDs must be unique")
    return document


def _schema_map(manifest: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in manifest.get("schemas", ()):
        store = str(item["store"])
        if store in result:
            raise UpgradePlanError(f"duplicate schema store in manifest: {store}")
        result[store] = str(item["version"])
    return result


def _provider_map(manifest: Mapping[str, Any]) -> dict[str, tuple[bool, str | None]]:
    return {
        str(item["provider_id"]): (
            bool(item["enabled"]),
            item.get("capability_bundle_revision"),
        )
        for item in manifest.get("providers", ())
    }


def _configuration_changes(
    current: Mapping[str, Any],
    target: Mapping[str, Any],
) -> tuple[str, ...]:
    before = dict(current["configuration"])
    after = dict(target["configuration"])
    return tuple(
        key
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    )


def _provider_changes(
    current: Mapping[str, Any],
    target: Mapping[str, Any],
) -> tuple[str, ...]:
    before = _provider_map(current)
    after = _provider_map(target)
    return tuple(
        provider
        for provider in sorted(set(before) | set(after))
        if before.get(provider) != after.get(provider)
    )


def _checkpoint_status(
    *,
    current_identity: str,
    receipt: Mapping[str, Any] | None,
) -> tuple[str | None, list[str]]:
    blockers: list[str] = []
    if receipt is None:
        return None, ["pre_upgrade_checkpoint_missing"]
    if receipt.get("schema_version") != "1.0":
        blockers.append("checkpoint_schema_invalid")
    if receipt.get("source_deployment_identity_sha256") != current_identity:
        blockers.append("checkpoint_identity_mismatch")
    digest = str(receipt.get("recovery_package_sha256") or "").lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        blockers.append("checkpoint_package_digest_invalid")
        digest = ""
    if receipt.get("verified") is not True:
        blockers.append("checkpoint_not_verified")
    if receipt.get("restorable") is not True:
        blockers.append("checkpoint_not_restorable")
    return digest or None, blockers


def _migration_index(catalog: Mapping[str, Any]) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for item in catalog.get("migrations", ()):
        key = (
            str(item["store"]),
            str(item["from_version"]),
            str(item["to_version"]),
        )
        if key in result:
            raise UpgradePlanError(
                "duplicate migration edge: " + "|".join(key)
            )
        result[key] = item
    return result


def plan_upgrade(
    *,
    current_manifest: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
    migration_catalog: Mapping[str, Any],
    checkpoint_receipt: Mapping[str, Any] | None,
) -> UpgradePlan:
    current = validate_deployment_manifest(current_manifest)
    target = validate_deployment_manifest(target_manifest)

    blockers: list[str] = []
    if current["environment"] != "candidate" or target["environment"] != "candidate":
        blockers.append("non_candidate_upgrade_not_supported")
    if current["instance_id"] != target["instance_id"]:
        blockers.append("instance_identity_mismatch")
    if current["runtime"]["architecture"] != target["runtime"]["architecture"]:
        blockers.append("architecture_change_not_supported")

    current_identity = str(current["identity_sha256"])
    target_identity = str(target["identity_sha256"])
    checkpoint_digest, checkpoint_blockers = _checkpoint_status(
        current_identity=current_identity,
        receipt=checkpoint_receipt,
    )
    blockers.extend(checkpoint_blockers)

    current_schemas = _schema_map(current)
    target_schemas = _schema_map(target)
    migration_edges = _migration_index(migration_catalog)
    migrations: list[MigrationStep] = []

    for store in sorted(set(current_schemas) | set(target_schemas)):
        before = current_schemas.get(store)
        after = target_schemas.get(store)
        if before == after:
            continue
        if before is None:
            blockers.append("new_schema_store_requires_declared_initializer:" + store)
            continue
        if after is None:
            blockers.append("schema_store_removal_not_supported:" + store)
            continue
        edge = migration_edges.get((store, before, after))
        if edge is None:
            blockers.append(
                "migration_edge_missing:" + store + ":" + before + "->" + after
            )
            continue
        migrations.append(
            MigrationStep(
                migration_id=str(edge["id"]),
                store=store,
                from_version=before,
                to_version=after,
                reversible=bool(edge["reversible"]),
                rollback_strategy=str(edge["rollback_strategy"]),
            )
        )

    config_changes = _configuration_changes(current, target)
    provider_changes = _provider_changes(current, target)

    if not migrations and not config_changes and not provider_changes:
        rollback_mode = "code_only"
        automatic_rollback_safe = True
    elif migrations and all(
        item.reversible and item.rollback_strategy == "reverse_migration"
        for item in migrations
    ):
        rollback_mode = "reverse_migrations_then_restore_configuration"
        automatic_rollback_safe = bool(checkpoint_digest)
    else:
        rollback_mode = "restore_checkpoint"
        automatic_rollback_safe = False

    if target_identity == current_identity:
        blockers.append("target_deployment_identity_unchanged")

    material = {
        "schema_version": "1.0",
        "current_deployment_identity_sha256": current_identity,
        "target_deployment_identity_sha256": target_identity,
        "instance_id": str(current["instance_id"]),
        "environment": str(current["environment"]),
        "current_source_sha": str(current["platform"]["source_sha"]),
        "target_source_sha": str(target["platform"]["source_sha"]),
        "current_artifact_digest": str(current["platform"]["artifact_digest"]),
        "target_artifact_digest": str(target["platform"]["artifact_digest"]),
        "checkpoint_recovery_package_sha256": checkpoint_digest,
        "configuration_changes": list(config_changes),
        "provider_changes": list(provider_changes),
        "migrations": [asdict(item) for item in migrations],
        "rollback_mode": rollback_mode,
        "automatic_rollback_safe": automatic_rollback_safe,
        "blockers": sorted(set(blockers)),
    }
    plan_hash = canonical_sha256(material)

    return UpgradePlan(
        schema_version="1.0",
        current_deployment_identity_sha256=current_identity,
        target_deployment_identity_sha256=target_identity,
        instance_id=str(current["instance_id"]),
        environment=str(current["environment"]),
        current_source_sha=str(current["platform"]["source_sha"]),
        target_source_sha=str(target["platform"]["source_sha"]),
        current_artifact_digest=str(current["platform"]["artifact_digest"]),
        target_artifact_digest=str(target["platform"]["artifact_digest"]),
        checkpoint_recovery_package_sha256=checkpoint_digest,
        configuration_changes=config_changes,
        provider_changes=provider_changes,
        migrations=tuple(migrations),
        rollback_mode=rollback_mode,
        automatic_rollback_safe=automatic_rollback_safe,
        blockers=tuple(sorted(set(blockers))),
        status="ready_for_upgrade" if not blockers else "blocked",
        plan_sha256=plan_hash,
    )


def plan_rollback(plan: UpgradePlan) -> RollbackPlan:
    blockers: list[str] = []
    reverse: tuple[str, ...] = ()
    checkpoint = plan.checkpoint_recovery_package_sha256
    automatic = False

    if plan.status != "ready_for_upgrade":
        blockers.append("upgrade_plan_not_ready")

    if plan.rollback_mode == "code_only":
        automatic = True
    elif plan.rollback_mode == "reverse_migrations_then_restore_configuration":
        reverse = tuple(
            item.migration_id for item in reversed(plan.migrations)
        )
        if not checkpoint:
            blockers.append("checkpoint_required_for_configuration_restore")
        else:
            automatic = True
    elif plan.rollback_mode == "restore_checkpoint":
        if not checkpoint:
            blockers.append("checkpoint_required_for_state_restore")
        automatic = False
    else:
        blockers.append("unknown_rollback_mode")

    return RollbackPlan(
        schema_version="1.0",
        upgrade_plan_sha256=plan.plan_sha256,
        mode=plan.rollback_mode,
        current_deployment_identity_sha256=plan.current_deployment_identity_sha256,
        failed_target_deployment_identity_sha256=plan.target_deployment_identity_sha256,
        reverse_migrations=reverse,
        recovery_package_sha256=checkpoint,
        automatic=automatic and not blockers,
        blockers=tuple(blockers),
        status="ready_for_rollback" if not blockers else "blocked",
    )


def _atomic_current_link(root: Path, source_sha: str) -> None:
    current = root / "opt/jason/current"
    current.parent.mkdir(parents=True, exist_ok=True)
    temporary = current.with_name(".current.upgrade")
    if temporary.exists() or temporary.is_symlink():
        temporary.unlink()
    temporary.symlink_to(Path("releases") / source_sha)
    temporary.replace(current)


def _write_manifest_atomic(root: Path, manifest: Mapping[str, Any]) -> None:
    output = root / "var/lib/jason/deployment-manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(".deployment-manifest.upgrade.json")
    temporary.write_text(
        json.dumps(dict(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)


def execute_candidate_upgrade(
    *,
    target_root: str | Path,
    plan: UpgradePlan,
    current_manifest: Mapping[str, Any],
    target_manifest: Mapping[str, Any],
    migration_apply,
    migration_reverse,
    verify_target,
    checkpoint_restore=None,
    authorize_checkpoint_restore: bool = False,
    candidate_identity: CandidateHostIdentity | None = None,
) -> dict[str, Any]:
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="candidate upgrade execution",
    )
    if plan.status != "ready_for_upgrade":
        raise UpgradePlanError(
            "candidate upgrade plan is not ready: " + ",".join(plan.blockers)
        )

    current = validate_deployment_manifest(current_manifest)
    target = validate_deployment_manifest(target_manifest)
    if current["identity_sha256"] != plan.current_deployment_identity_sha256:
        raise UpgradePlanError("current manifest does not match upgrade plan")
    if target["identity_sha256"] != plan.target_deployment_identity_sha256:
        raise UpgradePlanError("target manifest does not match upgrade plan")

    current_link = root / "opt/jason/current"
    expected_current = root / "opt/jason/releases" / plan.current_source_sha
    target_release = root / "opt/jason/releases" / plan.target_source_sha
    if not current_link.is_symlink() or current_link.resolve() != expected_current:
        raise UpgradePlanError("current release link does not match upgrade plan")
    if not target_release.is_dir():
        raise UpgradePlanError("target release is not staged")

    manifest_path = root / "var/lib/jason/deployment-manifest.json"
    if not manifest_path.is_file():
        raise UpgradePlanError("current deployment manifest file is missing")
    current_manifest_bytes = manifest_path.read_bytes()

    applied: list[MigrationStep] = []
    _atomic_current_link(root, plan.target_source_sha)
    _write_manifest_atomic(root, target)

    try:
        for step in plan.migrations:
            migration_apply(step, root)
            applied.append(step)
        verified = bool(verify_target(target, root))
        if not verified:
            raise UpgradePlanError("post-upgrade verification failed")
    except Exception as failure:
        if plan.rollback_mode == "code_only":
            _atomic_current_link(root, plan.current_source_sha)
            manifest_path.write_bytes(current_manifest_bytes)
            return {
                "status": "rolled_back",
                "rollback_mode": "code_only",
                "failure": str(failure),
                "applied_migrations": [item.migration_id for item in applied],
                "current_source_sha": plan.current_source_sha,
            }

        if plan.rollback_mode == "reverse_migrations_then_restore_configuration":
            for step in reversed(applied):
                migration_reverse(step, root)
            _atomic_current_link(root, plan.current_source_sha)
            manifest_path.write_bytes(current_manifest_bytes)
            return {
                "status": "rolled_back",
                "rollback_mode": plan.rollback_mode,
                "failure": str(failure),
                "reversed_migrations": [
                    item.migration_id for item in reversed(applied)
                ],
                "current_source_sha": plan.current_source_sha,
            }

        if plan.rollback_mode == "restore_checkpoint":
            if not authorize_checkpoint_restore or checkpoint_restore is None:
                return {
                    "status": "checkpoint_restore_required",
                    "rollback_mode": "restore_checkpoint",
                    "failure": str(failure),
                    "recovery_package_sha256": (
                        plan.checkpoint_recovery_package_sha256
                    ),
                    "automatic_rollback_performed": False,
                }
            checkpoint_restore(
                plan.checkpoint_recovery_package_sha256,
                root,
            )
            _atomic_current_link(root, plan.current_source_sha)
            manifest_path.write_bytes(current_manifest_bytes)
            return {
                "status": "rolled_back",
                "rollback_mode": "restore_checkpoint",
                "failure": str(failure),
                "recovery_package_sha256": (
                    plan.checkpoint_recovery_package_sha256
                ),
                "automatic_rollback_performed": False,
                "explicit_checkpoint_restore_authorized": True,
            }

        raise

    return {
        "status": "upgraded",
        "current_source_sha": plan.target_source_sha,
        "deployment_identity_sha256": plan.target_deployment_identity_sha256,
        "applied_migrations": [item.migration_id for item in applied],
        "rollback_mode": plan.rollback_mode,
    }
