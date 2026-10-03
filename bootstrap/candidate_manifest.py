from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tomllib
from typing import Any, Mapping

from bootstrap.clean_install import HostObservation
from bootstrap.install_runtime import ReleaseStageResult, StateStoreResult
from tools.deployment_manifest import (
    ComponentIdentity,
    DeploymentManifestInputs,
    ProviderIdentity,
    RuntimeIdentity,
    SchemaIdentity,
    build_deployment_manifest,
    canonical_json_bytes,
)


class CandidateManifestError(ValueError):
    pass


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def released_platform_version(release_path: str | Path) -> str:
    pyproject = Path(release_path) / "implementation/pyproject.toml"
    try:
        payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        raise CandidateManifestError(
            "staged release is missing a valid implementation/pyproject.toml"
        ) from exc
    version = str(payload.get("project", {}).get("version") or "").strip()
    if not version:
        raise CandidateManifestError("staged release project version is missing")
    return version


def released_playbook_revision(release_path: str | Path) -> str:
    registry = (
        Path(release_path)
        / "implementation/autonomous_remediation/playbook_registry.json"
    )
    try:
        payload = json.loads(registry.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise CandidateManifestError(
            "staged release playbook registry is missing or invalid"
        ) from exc
    return _canonical_sha256(payload)


def sqlite_schema_sha256(path: str | Path) -> str:
    db = Path(path)
    if not db.is_file():
        raise CandidateManifestError(f"SQLite store is missing: {db}")
    with sqlite3.connect(db) as connection:
        rows = connection.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE sql IS NOT NULL
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type, name, tbl_name
            """
        ).fetchall()
    material = [
        {
            "type": str(row[0]),
            "name": str(row[1]),
            "table": str(row[2]),
            "sql": str(row[3]),
        }
        for row in rows
    ]
    if not material:
        raise CandidateManifestError(f"SQLite store has no schema objects: {db}")
    return _canonical_sha256(material)


def deployment_descriptor(
    *,
    instance_id: str,
    source_sha: str,
    artifact_sha256: str,
    resources: Mapping[str, Any],
    state_stores: tuple[StateStoreResult, ...],
) -> dict[str, Any]:
    if not instance_id.strip():
        raise CandidateManifestError("instance_id must be non-empty")
    portable_units = sorted(
        Path(str(unit["source"])).name
        for unit in resources["systemd_units"]
        if bool(unit["portable"])
    )
    required_networks = sorted(
        str(network["name"])
        for network in resources["networks"]
        if bool(network["required"])
    )
    initialized_stores = sorted(
        item.store_id
        for item in state_stores
        if item.status == "initialized"
    )
    return {
        "schema_version": "1.0",
        "environment": "candidate",
        "instance_id": instance_id.strip(),
        "source_sha": source_sha,
        "artifact_sha256": artifact_sha256,
        "required_networks": required_networks,
        "portable_systemd_units": portable_units,
        "bootstrap_initialized_state_stores": initialized_stores,
    }


def write_candidate_deployment_descriptor(
    *,
    target_root: str | Path,
    descriptor: Mapping[str, Any],
) -> tuple[Path, str]:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError("candidate deployment descriptor may not target /")
    path = root / "etc/jason/deployment.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(descriptor), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path, _canonical_sha256(dict(descriptor))


def _provider_identities(
    msp_configuration: Mapping[str, Any],
) -> tuple[ProviderIdentity, ...]:
    bundles = list(msp_configuration.get("capability_bundles") or ())
    bundle_revision = _canonical_sha256(bundles)
    providers = []
    for provider_id, raw in dict(
        msp_configuration.get("providers") or {}
    ).items():
        data = dict(raw or {})
        providers.append(
            ProviderIdentity(
                provider_id=str(provider_id),
                enabled=bool(data.get("enabled")),
                capability_bundle_revision=bundle_revision,
            )
        )
    return tuple(providers)


def _schema_identities(
    *,
    target_root: Path,
    state_stores: tuple[StateStoreResult, ...],
) -> tuple[SchemaIdentity, ...]:
    result = []
    for store in state_stores:
        if store.status != "initialized":
            continue
        path = target_root / store.relative_path
        result.append(
            SchemaIdentity(
                store=store.store_id,
                version="sha256:" + sqlite_schema_sha256(path),
            )
        )
    return tuple(result)


def generate_candidate_deployment_manifest(
    *,
    target_root: str | Path,
    instance_id: str,
    release: ReleaseStageResult,
    state_stores: tuple[StateStoreResult, ...],
    resources: Mapping[str, Any],
    msp_configuration: Mapping[str, Any],
    msp_configuration_revision: str,
    msp_policy_revision: str,
    host: HostObservation,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], Path]:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError("candidate deployment manifest may not target /")
    release_path = Path(release.release_path)
    version = released_platform_version(release_path)
    playbook_revision = released_playbook_revision(release_path)

    descriptor = deployment_descriptor(
        instance_id=instance_id,
        source_sha=release.source_sha,
        artifact_sha256=release.artifact_sha256,
        resources=resources,
        state_stores=state_stores,
    )
    _, deployment_revision = write_candidate_deployment_descriptor(
        target_root=root,
        descriptor=descriptor,
    )

    artifact_digest = "sha256:" + release.artifact_sha256
    inputs = DeploymentManifestInputs(
        deployment_id=(
            "candidate-"
            + instance_id.strip()
            + "-"
            + release.source_sha[:12]
        ),
        instance_id=instance_id.strip(),
        environment="candidate",
        release_version=version,
        source_sha=release.source_sha,
        artifact_digest=artifact_digest,
        deployment_revision=deployment_revision,
        msp_configuration_revision=msp_configuration_revision,
        msp_policy_revision=msp_policy_revision,
        playbook_revision=playbook_revision,
        components=(
            ComponentIdentity(
                name="core",
                kind="runtime",
                required=True,
                release_version=version,
                source_sha=release.source_sha,
                artifact_digest=artifact_digest,
            ),
        ),
        schemas=_schema_identities(
            target_root=root,
            state_stores=state_stores,
        ),
        providers=_provider_identities(msp_configuration),
        runtime=RuntimeIdentity(
            os=host.os_id + " " + host.os_version,
            architecture=host.architecture,
            python=host.python_version,
            container_runtime=host.docker_version or "not-required",
            compose=host.compose_version or "not-required",
        ),
    )
    manifest = build_deployment_manifest(
        inputs,
        generated_at=generated_at or datetime.now(timezone.utc),
    )
    output = root / "var/lib/jason/deployment-manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest, output
