from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
    validate_candidate_host_identity,
)
from tools.full_recovery_package import decrypt_recovery_package
from tools.full_recovery_restore import INTERNAL_MANIFEST_MEMBER


class CandidateSeedPackageError(ValueError):
    pass


_ALLOWED_STATE_CLASSES = {
    "provider-secrets",
    "signing-and-recovery-keys",
}
_REQUIRED_MEMBERS = {
    "secrets/openbao/raft/latest.snap",
    "secrets/openbao/raft/latest.snap.sha256",
    "secrets/openbao/init.json",
}


@dataclass(frozen=True, slots=True)
class CandidateSeedEntry:
    state_class: str
    member_name: str
    restore_relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class CandidateSeedInspection:
    schema_version: str
    source_deployment_identity_sha256: str
    entry_count: int
    restore_relative_paths: tuple[str, ...]
    entries: tuple[CandidateSeedEntry, ...]


def _safe_relative(value: str, *, label: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.strip():
        raise CandidateSeedPackageError(f"unsafe {label}: {value!r}")
    return path.as_posix()


def _load_recipient_private(path: str | Path) -> X25519PrivateKey:
    key = load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, X25519PrivateKey):
        raise CandidateSeedPackageError(
            "candidate seed recipient private key is not X25519"
        )
    return key


def _load_signer_public(path: str | Path) -> Ed25519PublicKey:
    key = load_pem_public_key(Path(path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise CandidateSeedPackageError(
            "candidate seed signer public key is not Ed25519"
        )
    return key


def _load_members(
    *,
    package_path: str | Path,
    recipient_private_key_path: str | Path,
    signer_public_key_path: str | Path,
) -> tuple[Mapping[str, Any], dict[str, bytes]]:
    package = json.loads(Path(package_path).read_text(encoding="utf-8"))
    members = decrypt_recovery_package(
        package,
        recipient_private_key=_load_recipient_private(
            recipient_private_key_path
        ),
        signer_public_key=_load_signer_public(signer_public_key_path),
    )
    return package, members


def inspect_candidate_seed_package(
    *,
    package_path: str | Path,
    recipient_private_key_path: str | Path,
    signer_public_key_path: str | Path,
    expected_source_deployment_identity_sha256: str,
) -> CandidateSeedInspection:
    package, members = _load_members(
        package_path=package_path,
        recipient_private_key_path=recipient_private_key_path,
        signer_public_key_path=signer_public_key_path,
    )
    expected = expected_source_deployment_identity_sha256.strip().lower()
    package_source = str(
        package.get("source_deployment_identity_sha256") or ""
    ).strip().lower()
    if package_source != expected:
        raise CandidateSeedPackageError(
            "candidate seed package source deployment identity mismatch"
        )

    raw_manifest = members.get(INTERNAL_MANIFEST_MEMBER)
    if raw_manifest is None:
        raise CandidateSeedPackageError(
            "candidate seed package is missing its recovery-state manifest"
        )
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateSeedPackageError(
            "candidate seed recovery-state manifest is invalid"
        ) from exc
    source = str(
        manifest.get("source_deployment_identity_sha256") or ""
    ).strip().lower()
    if source != expected:
        raise CandidateSeedPackageError(
            "candidate seed recovery-state identity mismatch"
        )

    entries: list[CandidateSeedEntry] = []
    included_members: set[str] = set()
    for raw in manifest.get("entries", ()):
        if not isinstance(raw, Mapping):
            continue
        state_class = str(raw.get("state_class") or "")
        if state_class not in _ALLOWED_STATE_CLASSES:
            continue
        member = raw.get("member_name")
        restore = raw.get("restore_relative_path")
        digest = raw.get("sha256")
        if member is None or restore is None or digest is None:
            continue
        member_name = _safe_relative(str(member), label="member name")
        restore_path = _safe_relative(
            str(restore),
            label="restore path",
        )
        payload = members.get(member_name)
        if payload is None:
            raise CandidateSeedPackageError(
                "candidate seed payload is missing: " + member_name
            )
        observed = hashlib.sha256(payload).hexdigest()
        if observed != str(digest):
            raise CandidateSeedPackageError(
                "candidate seed payload digest mismatch: " + member_name
            )
        if len(payload) != int(raw.get("size_bytes") or -1):
            raise CandidateSeedPackageError(
                "candidate seed payload size mismatch: " + member_name
            )
        entries.append(
            CandidateSeedEntry(
                state_class=state_class,
                member_name=member_name,
                restore_relative_path=restore_path,
                sha256=observed,
                size_bytes=len(payload),
            )
        )
        included_members.add(member_name)

    missing = sorted(_REQUIRED_MEMBERS - included_members)
    if missing:
        raise CandidateSeedPackageError(
            "candidate seed package is missing required OpenBao members: "
            + ",".join(missing)
        )

    return CandidateSeedInspection(
        schema_version="1.0",
        source_deployment_identity_sha256=expected,
        entry_count=len(entries),
        restore_relative_paths=tuple(
            sorted(item.restore_relative_path for item in entries)
        ),
        entries=tuple(entries),
    )


def stage_candidate_seed_package(
    *,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity,
    package_path: str | Path,
    recipient_private_key_path: str | Path,
    signer_public_key_path: str | Path,
    expected_source_deployment_identity_sha256: str,
) -> CandidateSeedInspection:
    validate_candidate_host_identity(candidate_identity)
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="candidate encrypted seed staging",
    )
    inspection = inspect_candidate_seed_package(
        package_path=package_path,
        recipient_private_key_path=recipient_private_key_path,
        signer_public_key_path=signer_public_key_path,
        expected_source_deployment_identity_sha256=(
            expected_source_deployment_identity_sha256
        ),
    )
    _, members = _load_members(
        package_path=package_path,
        recipient_private_key_path=recipient_private_key_path,
        signer_public_key_path=signer_public_key_path,
    )

    for entry in inspection.entries:
        target = root / entry.restore_relative_path
        payload = members[entry.member_name]
        if target.exists() or target.is_symlink():
            if (
                target.is_file()
                and not target.is_symlink()
                and hashlib.sha256(target.read_bytes()).hexdigest()
                == entry.sha256
            ):
                continue
            raise CandidateSeedPackageError(
                "candidate seed restore target already exists with different content: "
                + str(target)
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.parent.chmod(0o700)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".candidate-seed-",
            dir=target.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            os.chmod(target, 0o600)
        finally:
            temporary.unlink(missing_ok=True)

    return inspection
