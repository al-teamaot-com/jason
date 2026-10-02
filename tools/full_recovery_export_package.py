from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

from tools.full_recovery_export import (
    CollectionResult,
    ExternalAdapter,
    collect_full_recovery_state,
    collection_result_to_members,
)
from tools.full_recovery_package import create_recovery_package


def create_encrypted_full_recovery_export(
    *,
    target_root: str | Path,
    collection_spec: Mapping[str, Any],
    state_inventory: Mapping[str, Any],
    external_adapters: Mapping[str, ExternalAdapter],
    recipient_public_key: X25519PublicKey,
    recipient_key_id: str,
    signer_private_key: Ed25519PrivateKey,
    signer_key_id: str,
    created_at=None,
) -> tuple[dict[str, Any], CollectionResult]:
    collection = collect_full_recovery_state(
        target_root=target_root,
        collection_spec=collection_spec,
        state_inventory=state_inventory,
        external_adapters=external_adapters,
    )
    members = collection_result_to_members(collection)
    package = create_recovery_package(
        members=members,
        source_deployment_identity_sha256=collection.source_deployment_identity_sha256,
        recipient_public_key=recipient_public_key,
        recipient_key_id=recipient_key_id,
        signer_private_key=signer_private_key,
        signer_key_id=signer_key_id,
        created_at=created_at,
    )
    return package, collection


def write_recovery_package_atomic(
    package: Mapping[str, Any],
    *,
    output: str | Path,
) -> Path:
    path = Path(output)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"recovery package output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=".jason-recovery-export-",
        suffix=".json",
        dir=path.parent,
    )
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(package), handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return path
