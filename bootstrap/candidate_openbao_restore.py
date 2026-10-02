from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Any, Callable, Mapping, Sequence

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
    validate_candidate_host_identity,
)


class CandidateOpenBaoRestoreError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateOpenBaoCredential:
    provider_id: str
    role_name: str
    role_id_source: str
    credential_id_source: str
    role_id_target: str
    credential_id_target: str


@dataclass(frozen=True, slots=True)
class CandidateOpenBaoRestorePlan:
    schema_version: str
    instance_id: str
    target_root: str
    snapshot_source: str
    snapshot_sha256: str
    init_source: str
    candidate_snapshot: str
    candidate_init: str
    credentials: tuple[CandidateOpenBaoCredential, ...]


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
ApiCall = Callable[
    [str, str, str | None, Mapping[str, Any] | bytes | None],
    tuple[int, Mapping[str, Any]],
]


_PROVIDER_ROLES = {
    "autotask": "autotask-read-approle",
    "datto_rmm": "datto-rmm-read-approle",
}


def _private_regular(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CandidateOpenBaoRestoreError(f"{label} is unavailable: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise CandidateOpenBaoRestoreError(
            f"{label} permissions are too broad: {oct(mode)}"
        )
    return path.read_bytes()


def _protected_regular(path: Path, *, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise CandidateOpenBaoRestoreError(f"{label} is unavailable: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o037:
        raise CandidateOpenBaoRestoreError(
            f"{label} permissions are too broad: {oct(mode)}"
        )
    return path.read_bytes()


def _validate_init(data: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise CandidateOpenBaoRestoreError(
            "OpenBao initialization artifact is invalid JSON"
        ) from exc
    shares = payload.get("unseal_keys_b64")
    threshold = payload.get("unseal_threshold")
    if (
        not isinstance(shares, list)
        or not shares
        or not all(isinstance(item, str) and item for item in shares)
        or not isinstance(threshold, int)
        or threshold < 1
        or threshold > len(shares)
    ):
        raise CandidateOpenBaoRestoreError(
            "OpenBao initialization artifact is incomplete"
        )
    return payload


def _checksum(snapshot: bytes, sidecar: bytes) -> str:
    observed = hashlib.sha256(snapshot).hexdigest()
    try:
        expected = sidecar.decode("ascii").split()[0].strip().lower()
    except (UnicodeDecodeError, IndexError) as exc:
        raise CandidateOpenBaoRestoreError(
            "OpenBao snapshot checksum is invalid"
        ) from exc
    if observed != expected:
        raise CandidateOpenBaoRestoreError(
            "OpenBao snapshot checksum verification failed"
        )
    return observed


def build_candidate_openbao_restore_plan(
    *,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity,
    snapshot_path: str | Path,
    snapshot_checksum_path: str | Path,
    init_path: str | Path,
    approle_root: str | Path,
    provider_ids: Sequence[str],
) -> CandidateOpenBaoRestorePlan:
    validate_candidate_host_identity(candidate_identity)
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="candidate OpenBao restore plan",
    )
    snapshot = Path(snapshot_path)
    checksum = Path(snapshot_checksum_path)
    init = Path(init_path)
    snapshot_bytes = _private_regular(snapshot, label="OpenBao Raft snapshot")
    checksum_bytes = _private_regular(
        checksum, label="OpenBao snapshot checksum"
    )
    _validate_init(
        _private_regular(init, label="OpenBao initialization artifact")
    )
    observed = _checksum(snapshot_bytes, checksum_bytes)

    providers = tuple(sorted(set(str(item) for item in provider_ids)))
    unsupported = sorted(set(providers) - set(_PROVIDER_ROLES))
    if unsupported:
        raise CandidateOpenBaoRestoreError(
            "OpenBao candidate restore has no AppRole mapping for: "
            + ",".join(unsupported)
        )
    if not providers:
        raise CandidateOpenBaoRestoreError("at least one provider is required")

    source_root = Path(approle_root)
    target_base = root / "opt/jason/bootstrap/secrets/openbao"
    credentials: list[CandidateOpenBaoCredential] = []
    for provider in providers:
        role = _PROVIDER_ROLES[provider]
        role_source = source_root / role / "role-id"
        credential_source = source_root / role / "secret-id"
        _protected_regular(role_source, label=f"{provider} AppRole role ID")
        _protected_regular(
            credential_source, label=f"{provider} AppRole credential ID"
        )
        credentials.append(
            CandidateOpenBaoCredential(
                provider_id=provider,
                role_name=role,
                role_id_source=str(role_source),
                credential_id_source=str(credential_source),
                role_id_target=str(target_base / role / "role-id"),
                credential_id_target=str(target_base / role / "secret-id"),
            )
        )

    recovery = root / "var/lib/jason/recovery/openbao"
    return CandidateOpenBaoRestorePlan(
        schema_version="1.0",
        instance_id=candidate_identity.instance_id,
        target_root=str(root),
        snapshot_source=str(snapshot),
        snapshot_sha256=observed,
        init_source=str(init),
        candidate_snapshot=str(recovery / "source.snap"),
        candidate_init=str(target_base / "init.json"),
        credentials=tuple(credentials),
    )


def _stage_private(
    source: Path,
    destination: Path,
    *,
    allow_group_read: bool = False,
) -> None:
    if source.resolve() == destination.resolve(strict=False):
        return
    if destination.exists() or destination.is_symlink():
        raise CandidateOpenBaoRestoreError(
            f"candidate recovery destination already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.parent.chmod(0o700)
    temporary = destination.with_name("." + destination.name + ".staging")
    temporary.unlink(missing_ok=True)
    try:
        with source.open("rb") as src, temporary.open("xb") as dst:
            os.chmod(temporary, 0o600)
            shutil.copyfileobj(src, dst, length=65536)
            dst.flush()
            os.fsync(dst.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o640 if allow_group_read else 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _response_value(
    payload: Mapping[str, Any],
    section: str,
    name: str,
) -> str:
    nested = payload.get(section)
    value = nested.get(name) if isinstance(nested, Mapping) else None
    if not isinstance(value, str) or not value:
        raise CandidateOpenBaoRestoreError(
            f"OpenBao response is missing {section}.{name}"
        )
    return value


def restore_candidate_openbao(
    *,
    plan: CandidateOpenBaoRestorePlan,
    candidate_identity: CandidateHostIdentity,
    runner: Runner,
    api: ApiCall,
) -> dict[str, Any]:
    validate_candidate_host_identity(candidate_identity)
    if plan.instance_id != candidate_identity.instance_id:
        raise CandidateOpenBaoRestoreError(
            "OpenBao restore plan instance mismatch"
        )

    candidate_snapshot = Path(plan.candidate_snapshot)
    candidate_init = Path(plan.candidate_init)
    _stage_private(Path(plan.snapshot_source), candidate_snapshot)
    _stage_private(Path(plan.init_source), candidate_init)
    for item in plan.credentials:
        _stage_private(
            Path(item.role_id_source),
            Path(item.role_id_target),
            allow_group_read=True,
        )
        _stage_private(
            Path(item.credential_id_source),
            Path(item.credential_id_target),
            allow_group_read=True,
        )

    init = _validate_init(candidate_init.read_bytes())
    snapshot_bytes = candidate_snapshot.read_bytes()
    if hashlib.sha256(snapshot_bytes).hexdigest() != plan.snapshot_sha256:
        raise CandidateOpenBaoRestoreError(
            "staged OpenBao snapshot digest changed"
        )

    _, health = api("GET", "sys/health", None, None)
    if bool(health.get("initialized")):
        raise CandidateOpenBaoRestoreError(
            "candidate OpenBao must be uninitialized before restore"
        )

    initialized = runner(
        (
            "docker",
            "exec",
            "openbao",
            "bao",
            "operator",
            "init",
            "-key-shares=1",
            "-key-threshold=1",
            "-format=json",
        )
    )
    if initialized.returncode != 0:
        raise CandidateOpenBaoRestoreError(
            "temporary candidate OpenBao initialization failed"
        )
    try:
        temporary = json.loads(initialized.stdout)
        temporary_key = str(temporary["unseal_keys_b64"][0])
        temporary_authority = str(temporary["root_token"])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise CandidateOpenBaoRestoreError(
            "temporary OpenBao initialization result is incomplete"
        ) from exc

    status, result = api(
        "POST", "sys/unseal", None, {"key": temporary_key}
    )
    temporary_key = ""
    if status != 200 or bool(result.get("sealed")):
        raise CandidateOpenBaoRestoreError(
            "temporary candidate OpenBao unseal failed"
        )

    status, _ = api(
        "POST",
        "sys/storage/raft/snapshot-force",
        temporary_authority,
        snapshot_bytes,
    )
    temporary_authority = ""
    if status not in {200, 204}:
        raise CandidateOpenBaoRestoreError(
            "candidate OpenBao Raft restore failed"
        )

    result = {}
    for share in init["unseal_keys_b64"][: int(init["unseal_threshold"])]:
        status, result = api(
            "POST", "sys/unseal", None, {"key": str(share)}
        )
        if status != 200:
            raise CandidateOpenBaoRestoreError(
                "restored OpenBao rejected an unseal share"
            )
    if bool(result.get("sealed")):
        raise CandidateOpenBaoRestoreError(
            "restored OpenBao remained sealed"
        )

    validated: list[str] = []
    for item in plan.credentials:
        role_id = _protected_regular(
            Path(item.role_id_target),
            label=f"{item.provider_id} restored AppRole role ID",
        ).decode("utf-8").strip()
        credential_id = _protected_regular(
            Path(item.credential_id_target),
            label=f"{item.provider_id} restored AppRole credential ID",
        ).decode("utf-8").strip()
        status, login = api(
            "POST",
            "auth/approle/login",
            None,
            {"role_id": role_id, "secret_id": credential_id},
        )
        role_id = ""
        credential_id = ""
        if status != 200:
            raise CandidateOpenBaoRestoreError(
                f"restored AppRole login failed for {item.provider_id}"
            )
        _response_value(login, "auth", "client_token")
        validated.append(item.provider_id)

    return {
        "status": "candidate_openbao_restored",
        "instance_id": plan.instance_id,
        "snapshot_sha256": plan.snapshot_sha256,
        "providers_validated": validated,
        "temporary_authority_exposed_in_command": False,
        "new_provider_credentials_issued": False,
    }
