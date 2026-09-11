from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import stat
from typing import Iterable


DEFAULT_BOOTSTRAP_ROOT = Path("/opt/jason/bootstrap/secrets/openbao")
DEFAULT_RUNTIME_HOST_ROOT = Path("/run/jason-runtime-credentials/openbao")
DEFAULT_RUNTIME_UID = 1000
DEFAULT_RUNTIME_GID = 1000
_PRIVATE_SOURCE_MASK = 0o077
_RUNTIME_FILE_MODE = 0o400
_RUNTIME_DIRECTORY_MODE = 0o700


class ProviderRuntimeCredentialError(RuntimeError):
    """Safe local staging failure. Credential values must never appear in messages."""


@dataclass(frozen=True, slots=True)
class ProviderRuntimeCredentialSpec:
    provider: str
    credential_name: str
    source: Path
    destination: Path


@dataclass(frozen=True, slots=True)
class CredentialMetadata:
    path: Path
    owner_uid: int
    owner_gid: int
    mode: int


_PROVIDER_LAYOUT = {
    "it_glue": ("itglue-read-approle", "it-glue"),
    "autotask": ("autotask-read-approle", "autotask"),
}


def build_provider_read_specs(
    *,
    bootstrap_root: Path = DEFAULT_BOOTSTRAP_ROOT,
    runtime_host_root: Path = DEFAULT_RUNTIME_HOST_ROOT,
) -> tuple[ProviderRuntimeCredentialSpec, ...]:
    specs: list[ProviderRuntimeCredentialSpec] = []
    for provider, (bootstrap_dir, runtime_dir) in _PROVIDER_LAYOUT.items():
        for source_name, destination_name in (
            ("role-id", "role_id"),
            ("secret-id", "secret_id"),
        ):
            specs.append(
                ProviderRuntimeCredentialSpec(
                    provider=provider,
                    credential_name=destination_name,
                    source=bootstrap_root / bootstrap_dir / source_name,
                    destination=runtime_host_root / runtime_dir / destination_name,
                )
            )
    _validate_unique_paths(specs)
    return tuple(specs)


def inspect_private_source(
    path: Path,
    *,
    expected_owner_uid: int = 0,
) -> CredentialMetadata:
    """Inspect metadata only; do not open or read credential content."""
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise ProviderRuntimeCredentialError(
            f"credential source is unavailable: {path}"
        ) from exc
    if stat.S_ISLNK(info.st_mode):
        raise ProviderRuntimeCredentialError(
            f"credential source must not be a symlink: {path}"
        )
    if not stat.S_ISREG(info.st_mode):
        raise ProviderRuntimeCredentialError(
            f"credential source must be a regular file: {path}"
        )
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid != expected_owner_uid:
        raise ProviderRuntimeCredentialError(
            f"credential source owner is not approved: {path}"
        )
    if mode & _PRIVATE_SOURCE_MASK:
        raise ProviderRuntimeCredentialError(
            f"credential source permissions are too broad: {path}"
        )
    return CredentialMetadata(
        path=path,
        owner_uid=info.st_uid,
        owner_gid=info.st_gid,
        mode=mode,
    )


def preflight_provider_read_runtime_credentials(
    *,
    specs: Iterable[ProviderRuntimeCredentialSpec] | None = None,
    expected_source_owner_uid: int = 0,
) -> dict[str, object]:
    resolved = tuple(specs or build_provider_read_specs())
    _validate_unique_paths(resolved)
    sources = [
        inspect_private_source(
            item.source,
            expected_owner_uid=expected_source_owner_uid,
        )
        for item in resolved
    ]
    return {
        "providers": sorted({item.provider for item in resolved}),
        "credential_files": len(resolved),
        "source_metadata_valid": True,
        "source_content_read": False,
        "destination_content_written": False,
        "provider_network_contacted": False,
        "openbao_contacted": False,
        "credential_values_printed": False,
        "source_files_changed": False,
        "source_modes": sorted({f"{item.mode:04o}" for item in sources}),
        "status": "credential_staging_preflight_pass",
    }


def stage_provider_read_runtime_credentials(
    *,
    specs: Iterable[ProviderRuntimeCredentialSpec] | None = None,
    runtime_uid: int = DEFAULT_RUNTIME_UID,
    runtime_gid: int = DEFAULT_RUNTIME_GID,
    expected_source_owner_uid: int = 0,
    runtime_directory_owner_uid: int = 0,
    runtime_directory_owner_gid: int = 0,
    replace_existing: bool = False,
) -> dict[str, object]:
    """Create opaque runtime copies without changing root-owned bootstrap files."""
    if os.geteuid() != 0:
        raise PermissionError("provider runtime credential staging must run as root")
    if runtime_uid < 0 or runtime_gid < 0:
        raise ValueError("runtime uid/gid must be non-negative")

    resolved = tuple(specs or build_provider_read_specs())
    _validate_unique_paths(resolved)

    # Validate every source and destination before reading any credential bytes.
    source_metadata = {
        item.source: inspect_private_source(
            item.source,
            expected_owner_uid=expected_source_owner_uid,
        )
        for item in resolved
    }
    if not replace_existing:
        existing = [item.destination for item in resolved if os.path.lexists(item.destination)]
        if existing:
            raise ProviderRuntimeCredentialError(
                "runtime credential destination already exists; replacement requires explicit approval"
            )

    directories = sorted(
        {item.destination.parent for item in resolved},
        key=lambda item: (len(item.parts), str(item)),
    )
    runtime_root = _runtime_root_for_specs(resolved)
    all_directories: set[Path] = set()
    for directory in directories:
        current = directory
        while True:
            all_directories.add(current)
            if current == runtime_root:
                break
            if current == current.parent:
                raise ProviderRuntimeCredentialError(
                    "runtime credential destinations do not share a safe staging root"
                )
            current = current.parent
    for directory in sorted(
        all_directories,
        key=lambda item: (len(item.parts), str(item)),
    ):
        _ensure_secure_directory(
            directory,
            owner_uid=runtime_directory_owner_uid,
            owner_gid=runtime_directory_owner_gid,
        )

    staged: list[Path] = []
    try:
        for item in resolved:
            _copy_opaque_credential(
                item.source,
                item.destination,
                source_metadata=source_metadata[item.source],
                runtime_uid=runtime_uid,
                runtime_gid=runtime_gid,
                replace_existing=replace_existing,
            )
            staged.append(item.destination)
    except Exception:
        # On initial staging only, partial output is safe to remove because no
        # pre-existing runtime credential could have been replaced.
        if not replace_existing:
            for path in staged:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        raise

    return {
        "providers": sorted({item.provider for item in resolved}),
        "credential_files": len(resolved),
        "source_metadata_valid": True,
        "source_content_read": True,
        "destination_content_written": True,
        "provider_network_contacted": False,
        "openbao_contacted": False,
        "credential_values_printed": False,
        "source_files_changed": False,
        "destination_owner_uid": runtime_uid,
        "destination_owner_gid": runtime_gid,
        "destination_mode": f"{_RUNTIME_FILE_MODE:04o}",
        "replace_existing": replace_existing,
        "status": "credential_staging_pass",
    }


def _runtime_root_for_specs(
    specs: Iterable[ProviderRuntimeCredentialSpec],
) -> Path:
    parents = [str(item.destination.parent) for item in specs]
    common = Path(os.path.commonpath(parents))
    if common == Path("/") or len(common.parts) < 3:
        raise ProviderRuntimeCredentialError(
            "runtime credential destination root is too broad"
        )
    return common


def _validate_unique_paths(specs: Iterable[ProviderRuntimeCredentialSpec]) -> None:
    resolved = tuple(specs)
    if not resolved:
        raise ValueError("at least one provider runtime credential spec is required")
    sources = [str(item.source) for item in resolved]
    destinations = [str(item.destination) for item in resolved]
    if len(sources) != len(set(sources)):
        raise ValueError("provider runtime credential sources must be unique")
    if len(destinations) != len(set(destinations)):
        raise ValueError("provider runtime credential destinations must be unique")
    for item in resolved:
        if not item.provider.strip() or not item.credential_name.strip():
            raise ValueError("provider and credential name are required")
        if item.source == item.destination:
            raise ValueError("bootstrap source and runtime destination must be distinct")


def _ensure_secure_directory(
    path: Path,
    *,
    owner_uid: int,
    owner_gid: int,
) -> None:
    if os.path.lexists(path):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ProviderRuntimeCredentialError(
                f"runtime credential directory is not a secure directory: {path}"
            )
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != owner_uid or info.st_gid != owner_gid:
            raise ProviderRuntimeCredentialError(
                f"runtime credential directory owner is not approved: {path}"
            )
        if mode & 0o077:
            raise ProviderRuntimeCredentialError(
                f"runtime credential directory permissions are too broad: {path}"
            )
        return

    parent = path.parent
    if parent != path and parent != Path("/") and not parent.exists():
        _ensure_secure_directory(
            parent,
            owner_uid=owner_uid,
            owner_gid=owner_gid,
        )
    os.mkdir(path, _RUNTIME_DIRECTORY_MODE)
    os.chown(path, owner_uid, owner_gid)
    os.chmod(path, _RUNTIME_DIRECTORY_MODE)


def _copy_opaque_credential(
    source: Path,
    destination: Path,
    *,
    source_metadata: CredentialMetadata,
    runtime_uid: int,
    runtime_gid: int,
    replace_existing: bool,
) -> None:
    if not replace_existing and os.path.lexists(destination):
        raise FileExistsError(f"runtime credential destination already exists: {destination}")

    source_flags = os.O_RDONLY
    source_flags |= getattr(os, "O_CLOEXEC", 0)
    source_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, source_flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ProviderRuntimeCredentialError(
                f"credential source must not be a symlink: {source}"
            ) from exc
        raise

    temporary: Path | None = None
    temp_fd: int | None = None
    try:
        current = os.fstat(source_fd)
        if not stat.S_ISREG(current.st_mode):
            raise ProviderRuntimeCredentialError(
                f"credential source changed type during staging: {source}"
            )
        current_path = os.lstat(source)
        if (current.st_dev, current.st_ino) != (
            current_path.st_dev,
            current_path.st_ino,
        ):
            raise ProviderRuntimeCredentialError(
                f"credential source changed during staging: {source}"
            )
        if current.st_uid != source_metadata.owner_uid:
            raise ProviderRuntimeCredentialError(
                f"credential source owner changed during staging: {source}"
            )
        if stat.S_IMODE(current.st_mode) != source_metadata.mode:
            raise ProviderRuntimeCredentialError(
                f"credential source permissions changed during staging: {source}"
            )

        for attempt in range(100):
            candidate = destination.parent / (
                f".{destination.name}.staging-{os.getpid()}-{attempt}"
            )
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                temp_fd = os.open(candidate, flags, 0o600)
                temporary = candidate
                break
            except FileExistsError:
                continue
        if temp_fd is None or temporary is None:
            raise ProviderRuntimeCredentialError(
                "could not allocate a private runtime credential staging file"
            )

        total_bytes = 0
        while True:
            chunk = os.read(source_fd, 65536)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > 16384:
                raise ProviderRuntimeCredentialError(
                    "credential source exceeds the bounded staging size"
                )
            _write_all(temp_fd, chunk)
        if total_bytes == 0:
            raise ProviderRuntimeCredentialError(
                "credential source is empty"
            )
        os.fchown(temp_fd, runtime_uid, runtime_gid)
        os.fchmod(temp_fd, _RUNTIME_FILE_MODE)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None

        if replace_existing:
            os.replace(temporary, destination)
            temporary = None
        else:
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"runtime credential destination appeared during staging: {destination}"
                ) from exc
            temporary.unlink()
            temporary = None

        installed = os.lstat(destination)
        if stat.S_ISLNK(installed.st_mode) or not stat.S_ISREG(installed.st_mode):
            raise ProviderRuntimeCredentialError(
                "runtime credential installation produced an invalid file type"
            )
        if installed.st_uid != runtime_uid or installed.st_gid != runtime_gid:
            raise ProviderRuntimeCredentialError(
                "runtime credential installation produced an invalid owner"
            )
        if stat.S_IMODE(installed.st_mode) != _RUNTIME_FILE_MODE:
            raise ProviderRuntimeCredentialError(
                "runtime credential installation produced invalid permissions"
            )
    finally:
        os.close(source_fd)
        if temp_fd is not None:
            os.close(temp_fd)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("runtime credential staging write failed")
        view = view[written:]
