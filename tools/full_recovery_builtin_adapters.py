from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.full_recovery_export import CollectedMetadata, CollectedPayload


class BuiltinRecoveryAdapterError(ValueError):
    pass


def _private_regular_file(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise BuiltinRecoveryAdapterError(f"{label} is unavailable: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise BuiltinRecoveryAdapterError(
            f"{label} permissions are too broad: {oct(mode)}"
        )
    return path.read_bytes()


def _latest_openbao_snapshot(root: Path) -> tuple[Path, Path, str]:
    backup_dir = root / "opt/jason/backups/openbao"
    snapshots = sorted(
        (
            path
            for path in backup_dir.glob("*.snap")
            if path.is_file() and not path.is_symlink()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not snapshots:
        raise BuiltinRecoveryAdapterError(
            "no governed OpenBao Raft snapshot is available"
        )
    snapshot = snapshots[0]
    sidecar = Path(str(snapshot) + ".sha256")
    if sidecar.is_symlink() or not sidecar.is_file():
        raise BuiltinRecoveryAdapterError(
            "OpenBao snapshot checksum sidecar is missing"
        )
    snapshot_bytes = _private_regular_file(
        snapshot,
        label="OpenBao Raft snapshot",
    )
    sidecar_bytes = _private_regular_file(
        sidecar,
        label="OpenBao snapshot checksum",
    )
    expected = sidecar_bytes.decode("ascii").split()[0].strip().lower()
    observed = hashlib.sha256(snapshot_bytes).hexdigest()
    if expected != observed:
        raise BuiltinRecoveryAdapterError(
            "OpenBao Raft snapshot checksum verification failed"
        )
    return snapshot, sidecar, observed


def governed_secret_export_adapter(
    source_id: str,
    source: Mapping[str, Any],
    root: Path,
) -> tuple[Sequence[CollectedPayload], Sequence[CollectedMetadata]]:
    snapshot, sidecar, digest = _latest_openbao_snapshot(root)
    snapshot_bytes = snapshot.read_bytes()
    sidecar_bytes = sidecar.read_bytes()
    return (
        (
            CollectedPayload(
                state_class="provider-secrets",
                member_name="secrets/openbao/raft/latest.snap",
                restore_relative_path="var/lib/jason/recovery/openbao/latest.snap",
                data=snapshot_bytes,
                metadata={
                    "adapter": "governed_secret_export",
                    "source": "openbao-raft-snapshot",
                    "sha256": digest,
                    "size_bytes": len(snapshot_bytes),
                },
            ),
            CollectedPayload(
                state_class="provider-secrets",
                member_name="secrets/openbao/raft/latest.snap.sha256",
                restore_relative_path="var/lib/jason/recovery/openbao/latest.snap.sha256",
                data=sidecar_bytes,
                metadata={
                    "adapter": "governed_secret_export",
                    "source": "openbao-raft-checksum",
                },
            ),
        ),
        (),
    )


def _validate_openbao_init(data: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise BuiltinRecoveryAdapterError(
            "OpenBao initialization artifact is invalid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise BuiltinRecoveryAdapterError(
            "OpenBao initialization artifact must be an object"
        )
    shares = payload.get("unseal_keys_b64")
    threshold = payload.get("unseal_threshold")
    declared = payload.get("unseal_shares")
    if (
        not isinstance(shares, list)
        or not shares
        or not all(isinstance(item, str) and item for item in shares)
        or not isinstance(threshold, int)
        or threshold < 1
        or declared != len(shares)
        or threshold > len(shares)
    ):
        raise BuiltinRecoveryAdapterError(
            "OpenBao initialization artifact has invalid recovery structure"
        )
    return payload


def governed_key_export_adapter(
    source_id: str,
    source: Mapping[str, Any],
    root: Path,
) -> tuple[Sequence[CollectedPayload], Sequence[CollectedMetadata]]:
    init_path = root / "opt/jason/bootstrap/secrets/openbao/init.json"
    init_bytes = _private_regular_file(
        init_path,
        label="OpenBao initialization artifact",
    )
    init = _validate_openbao_init(init_bytes)

    payloads: list[CollectedPayload] = [
        CollectedPayload(
            state_class="signing-and-recovery-keys",
            member_name="secrets/openbao/init.json",
            restore_relative_path="opt/jason/bootstrap/secrets/openbao/init.json",
            data=init_bytes,
            metadata={
                "adapter": "governed_key_export",
                "source": "openbao-init",
                "share_count": int(init["unseal_shares"]),
                "threshold": int(init["unseal_threshold"]),
                "protected_values_exposed": False,
            },
        )
    ]

    trusted = root / "var/lib/jason/openclaw/trusted-keys"
    if trusted.exists():
        if trusted.is_symlink() or not trusted.is_dir():
            raise BuiltinRecoveryAdapterError(
                "trusted-key registry path is not a safe directory"
            )
        for child in sorted(trusted.rglob("*")):
            if child.is_symlink():
                raise BuiltinRecoveryAdapterError(
                    f"trusted-key directory contains symlink: {child}"
                )
            if not child.is_file():
                continue
            relative = child.relative_to(trusted)
            data = _private_regular_file(
                child,
                label="trusted-key material",
            )
            payloads.append(
                CollectedPayload(
                    state_class="signing-and-recovery-keys",
                    member_name="secrets/trusted-keys/" + relative.as_posix(),
                    restore_relative_path=(
                        Path("var/lib/jason/openclaw/trusted-keys") / relative
                    ).as_posix(),
                    data=data,
                    metadata={
                        "adapter": "governed_key_export",
                        "source": "trusted-key-material",
                    },
                )
            )

    return tuple(payloads), ()


BUILTIN_ADAPTERS = {
    "governed_secret_export": governed_secret_export_adapter,
    "governed_key_export": governed_key_export_adapter,
}


def discover_builtin_adapter_names(target_root: str | Path) -> tuple[str, ...]:
    root = Path(target_root)
    available: list[str] = []
    try:
        _latest_openbao_snapshot(root)
    except Exception:
        pass
    else:
        available.append("governed_secret_export")

    try:
        data = _private_regular_file(
            root / "opt/jason/bootstrap/secrets/openbao/init.json",
            label="OpenBao initialization artifact",
        )
        _validate_openbao_init(data)
    except Exception:
        pass
    else:
        available.append("governed_key_export")
    return tuple(sorted(available))
