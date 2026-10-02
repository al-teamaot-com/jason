from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_file_sha256(path: str | Path) -> str:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_source_sha(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 40 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError("source SHA must be 40 lowercase hexadecimal characters")
    return normalized


def _require_artifact_digest(value: str) -> str:
    normalized = value.strip().lower()
    prefix = "sha256:"
    body = normalized[len(prefix):] if normalized.startswith(prefix) else ""
    if len(body) != 64 or any(c not in "0123456789abcdef" for c in body):
        raise ValueError("artifact digest must be sha256:<64 hex characters>")
    return normalized


def _require_sha256(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError(f"{label} must be a 64-character SHA-256 digest")
    return normalized


@dataclass(frozen=True, slots=True)
class ComponentIdentity:
    name: str
    kind: str
    required: bool
    release_version: str
    source_sha: str
    artifact_digest: str

    def normalized(self) -> "ComponentIdentity":
        if not self.name.strip() or not self.kind.strip() or not self.release_version.strip():
            raise ValueError("component identity fields must be non-empty")
        return ComponentIdentity(
            name=self.name.strip(),
            kind=self.kind.strip(),
            required=bool(self.required),
            release_version=self.release_version.strip(),
            source_sha=_require_source_sha(self.source_sha),
            artifact_digest=_require_artifact_digest(self.artifact_digest),
        )


@dataclass(frozen=True, slots=True)
class SchemaIdentity:
    store: str
    version: str


@dataclass(frozen=True, slots=True)
class ProviderIdentity:
    provider_id: str
    enabled: bool
    capability_bundle_revision: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    os: str
    architecture: str
    python: str
    container_runtime: str
    compose: str


@dataclass(frozen=True, slots=True)
class DeploymentManifestInputs:
    deployment_id: str
    instance_id: str
    environment: str
    release_version: str
    source_sha: str
    artifact_digest: str
    deployment_revision: str
    msp_configuration_revision: str
    msp_policy_revision: str
    playbook_revision: str
    components: tuple[ComponentIdentity, ...]
    schemas: tuple[SchemaIdentity, ...]
    providers: tuple[ProviderIdentity, ...]
    runtime: RuntimeIdentity


def _identity_material(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"generated_at", "identity_sha256"}
    }


def deployment_identity_sha256(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(_identity_material(manifest))
    ).hexdigest()


def build_deployment_manifest(
    inputs: DeploymentManifestInputs,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    environment = inputs.environment.strip().lower()
    if environment not in {"development", "candidate", "production"}:
        raise ValueError("unsupported deployment environment")
    for value, label in (
        (inputs.deployment_id, "deployment_id"),
        (inputs.instance_id, "instance_id"),
        (inputs.release_version, "release_version"),
    ):
        if not value.strip():
            raise ValueError(f"{label} must be non-empty")

    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")

    components = [asdict(item.normalized()) for item in inputs.components]
    components.sort(key=lambda item: (item["kind"], item["name"]))

    schemas = [asdict(item) for item in inputs.schemas]
    if any(not item["store"].strip() or not item["version"].strip() for item in schemas):
        raise ValueError("schema identities must be non-empty")
    schemas.sort(key=lambda item: item["store"])

    providers = [asdict(item) for item in inputs.providers]
    if any(not item["provider_id"].strip() for item in providers):
        raise ValueError("provider_id must be non-empty")
    providers.sort(key=lambda item: item["provider_id"])

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "deployment_id": inputs.deployment_id.strip(),
        "instance_id": inputs.instance_id.strip(),
        "environment": environment,
        "generated_at": timestamp.astimezone(timezone.utc).isoformat(),
        "platform": {
            "release_version": inputs.release_version.strip(),
            "source_sha": _require_source_sha(inputs.source_sha),
            "artifact_digest": _require_artifact_digest(inputs.artifact_digest),
        },
        "configuration": {
            "deployment_revision": _require_sha256(
                inputs.deployment_revision, "deployment_revision"
            ),
            "msp_configuration_revision": _require_sha256(
                inputs.msp_configuration_revision, "msp_configuration_revision"
            ),
            "msp_policy_revision": _require_sha256(
                inputs.msp_policy_revision, "msp_policy_revision"
            ),
            "playbook_revision": _require_sha256(
                inputs.playbook_revision, "playbook_revision"
            ),
        },
        "components": components,
        "schemas": schemas,
        "providers": providers,
        "runtime": asdict(inputs.runtime),
    }
    if any(not str(value).strip() for value in manifest["runtime"].values()):
        raise ValueError("runtime identity fields must be non-empty")
    manifest["identity_sha256"] = deployment_identity_sha256(manifest)
    return manifest


def render_deployment_manifest(manifest: Mapping[str, Any]) -> str:
    platform = manifest["platform"]
    config = manifest["configuration"]
    lines = [
        f"Jason {platform['release_version']}",
        f"Deployment: {manifest['deployment_id']} ({manifest['environment']})",
        f"Instance: {manifest['instance_id']}",
        f"Source SHA: {platform['source_sha']}",
        f"Artifact: {platform['artifact_digest']}",
        f"Manifest identity: {manifest['identity_sha256']}",
        f"MSP config: {config['msp_configuration_revision']}",
        f"MSP policy: {config['msp_policy_revision']}",
        "Components:",
    ]
    for component in manifest.get("components", ()):
        lines.append(
            "  - "
            + component["name"]
            + " "
            + component["release_version"]
            + " "
            + component["source_sha"]
            + " "
            + component["artifact_digest"]
        )
    return "\n".join(lines)
