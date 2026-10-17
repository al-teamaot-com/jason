from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class DeploymentManifestError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _identity_material(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in manifest.items()
        if key not in {"generated_at", "identity_sha256"}
    }


def expected_identity_sha256(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(_identity_material(manifest))
    ).hexdigest()


def validate_deployment_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(manifest)
    observed = str(payload.get("identity_sha256") or "").strip().lower()
    if len(observed) != 64:
        raise DeploymentManifestError("deployment manifest identity is missing or invalid")
    expected = expected_identity_sha256(payload)
    if observed != expected:
        raise DeploymentManifestError("deployment manifest identity hash mismatch")

    platform = payload.get("platform")
    configuration = payload.get("configuration")
    if not isinstance(platform, Mapping):
        raise DeploymentManifestError("deployment manifest platform identity is missing")
    if not isinstance(configuration, Mapping):
        raise DeploymentManifestError("deployment manifest configuration identity is missing")
    if not str(platform.get("source_sha") or "").strip():
        raise DeploymentManifestError("deployment manifest source SHA is missing")
    if not str(platform.get("artifact_digest") or "").strip():
        raise DeploymentManifestError("deployment manifest artifact digest is missing")
    if not str(configuration.get("msp_configuration_revision") or "").strip():
        raise DeploymentManifestError("deployment manifest MSP configuration revision is missing")
    if not str(configuration.get("msp_policy_revision") or "").strip():
        raise DeploymentManifestError("deployment manifest MSP policy revision is missing")
    return payload


class FileDeploymentManifestProvider:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DeploymentManifestError("deployment manifest file is unavailable") from exc
        except json.JSONDecodeError as exc:
            raise DeploymentManifestError("deployment manifest file is invalid JSON") from exc
        if not isinstance(raw, Mapping):
            raise DeploymentManifestError("deployment manifest must be a JSON object")
        return validate_deployment_manifest(raw)
