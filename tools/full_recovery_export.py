from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from jason_runtime.deployment_identity import FileDeploymentManifestProvider
from tools.full_recovery_restore import assemble_recovery_members


class FullRecoveryExportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CollectedPayload:
    state_class: str
    member_name: str
    restore_relative_path: str
    data: bytes
    metadata: Mapping[str, str | int | float | bool | None]


@dataclass(frozen=True, slots=True)
class CollectedMetadata:
    state_class: str
    metadata: Mapping[str, str | int | float | bool | None]


@dataclass(frozen=True, slots=True)
class CollectionResult:
    source_deployment_identity_sha256: str
    payloads: tuple[CollectedPayload, ...]
    metadata_only: tuple[CollectedMetadata, ...]
    optional_missing: tuple[str, ...]
    external_adapters_used: tuple[str, ...]


ExternalAdapter = Callable[
    [str, Mapping[str, Any], Path],
    tuple[Sequence[CollectedPayload], Sequence[CollectedMetadata]],
]


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_collection_spec(
    document_path: str | Path,
    schema_path: str | Path,
) -> dict[str, Any]:
    document = _load_json(document_path)
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        raise FullRecoveryExportError(
            "recovery collection spec invalid: " + first.message
        )
    ids = [str(item["id"]) for item in document["sources"]]
    if len(ids) != len(set(ids)):
        raise FullRecoveryExportError("recovery collection source IDs must be unique")
    return document


def _inventory_by_class(
    inventory: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    return {
        str(item["state_class"]): item
        for item in inventory.get("classes", ())
    }


def _safe_relative(value: str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.strip():
        raise FullRecoveryExportError(f"unsafe {label}: {value!r}")
    return path


def _member_name(source_id: str, suffix: str = "") -> str:
    base = "state/" + source_id
    return base if not suffix else base + "/" + suffix


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FullRecoveryExportError(
            f"recovery source is not a regular file: {path}"
        )
    return path.read_bytes()


def _sqlite_snapshot(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FullRecoveryExportError(
            f"SQLite recovery source is unavailable: {path}"
        )
    fd, temp_name = tempfile.mkstemp(prefix=".jason-recovery-sqlite-")
    os.close(fd)
    temp = Path(temp_name)
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as source:
            with sqlite3.connect(temp) as destination:
                source.backup(destination)
                integrity = destination.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0]
                if integrity != "ok":
                    raise FullRecoveryExportError(
                        f"SQLite recovery snapshot failed integrity check: {path}"
                    )
        return temp.read_bytes()
    finally:
        temp.unlink(missing_ok=True)


def _directory_payloads(
    *,
    source_id: str,
    state_class: str,
    source: Path,
    restore_base: Path,
) -> list[CollectedPayload]:
    if source.is_symlink() or not source.is_dir():
        raise FullRecoveryExportError(
            f"recovery directory source is unavailable: {source}"
        )
    payloads: list[CollectedPayload] = []
    for child in sorted(source.rglob("*")):
        if child.is_symlink():
            raise FullRecoveryExportError(
                f"recovery directory contains symlink: {child}"
            )
        if not child.is_file():
            continue
        relative = child.relative_to(source)
        payloads.append(
            CollectedPayload(
                state_class=state_class,
                member_name=_member_name(source_id, relative.as_posix()),
                restore_relative_path=(restore_base / relative).as_posix(),
                data=child.read_bytes(),
                metadata={"collector": "directory_files"},
            )
        )
    return payloads


def collect_full_recovery_state(
    *,
    target_root: str | Path,
    collection_spec: Mapping[str, Any],
    state_inventory: Mapping[str, Any],
    external_adapters: Mapping[str, ExternalAdapter] | None = None,
) -> CollectionResult:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError(
            "non-production full recovery exporter may not target the live filesystem root"
        )
    if not root.is_absolute():
        raise FullRecoveryExportError("target_root must be absolute")

    manifest = FileDeploymentManifestProvider(
        root / "var/lib/jason/deployment-manifest.json"
    ).read()
    source_identity = str(manifest["identity_sha256"])
    classes = _inventory_by_class(state_inventory)
    adapters = dict(external_adapters or {})

    payloads: list[CollectedPayload] = []
    metadata_only: list[CollectedMetadata] = []
    optional_missing: list[str] = []
    adapters_used: list[str] = []

    for raw in collection_spec["sources"]:
        source_id = str(raw["id"])
        state_class = str(raw["state_class"])
        strategy = str(raw["strategy"])
        required = bool(raw["required"])
        policy = classes.get(state_class)
        if policy is None:
            raise FullRecoveryExportError(
                f"collection source {source_id} uses unknown state class {state_class}"
            )

        if strategy in {"file", "sqlite_backup", "directory_files", "external_adapter"}:
            if not bool(policy["full_recovery_export"]):
                raise FullRecoveryExportError(
                    f"state class is not allowed in Full Recovery Export: {state_class}"
                )

        if strategy == "metadata_only":
            metadata_only.append(
                CollectedMetadata(
                    state_class=state_class,
                    metadata=dict(raw.get("metadata") or {}),
                )
            )
            continue

        if strategy == "external_adapter":
            adapter_name = str(raw.get("adapter") or "")
            adapter = adapters.get(adapter_name)
            if adapter is None:
                if required:
                    raise FullRecoveryExportError(
                        f"required recovery adapter unavailable: {adapter_name}"
                    )
                optional_missing.append(source_id)
                continue
            adapter_payloads, adapter_metadata = adapter(
                source_id,
                raw,
                root,
            )
            payloads.extend(adapter_payloads)
            metadata_only.extend(adapter_metadata)
            adapters_used.append(adapter_name)
            continue

        source_relative = _safe_relative(
            str(raw.get("source_relative_path") or ""),
            label="source path",
        )
        restore_relative = _safe_relative(
            str(raw.get("restore_relative_path") or ""),
            label="restore path",
        )
        source = root / source_relative

        if not source.exists():
            if required:
                raise FullRecoveryExportError(
                    f"required recovery source missing: {source_id}"
                )
            optional_missing.append(source_id)
            continue

        if strategy == "file":
            data = _read_regular_file(source)
            payloads.append(
                CollectedPayload(
                    state_class=state_class,
                    member_name=_member_name(source_id),
                    restore_relative_path=restore_relative.as_posix(),
                    data=data,
                    metadata={
                        "collector": "file",
                        "sha256": hashlib.sha256(data).hexdigest(),
                    },
                )
            )
            continue

        if strategy == "sqlite_backup":
            data = _sqlite_snapshot(source)
            payloads.append(
                CollectedPayload(
                    state_class=state_class,
                    member_name=_member_name(source_id),
                    restore_relative_path=restore_relative.as_posix(),
                    data=data,
                    metadata={
                        "collector": "sqlite_backup",
                        "sqlite_integrity": "ok",
                    },
                )
            )
            continue

        if strategy == "directory_files":
            payloads.extend(
                _directory_payloads(
                    source_id=source_id,
                    state_class=state_class,
                    source=source,
                    restore_base=restore_relative,
                )
            )
            continue

        raise FullRecoveryExportError(
            f"unsupported recovery collection strategy: {strategy}"
        )

    return CollectionResult(
        source_deployment_identity_sha256=source_identity,
        payloads=tuple(payloads),
        metadata_only=tuple(metadata_only),
        optional_missing=tuple(sorted(optional_missing)),
        external_adapters_used=tuple(sorted(set(adapters_used))),
    )


def collection_result_to_members(
    result: CollectionResult,
) -> dict[str, bytes]:
    return assemble_recovery_members(
        source_deployment_identity_sha256=result.source_deployment_identity_sha256,
        payloads=tuple(
            (
                item.state_class,
                item.member_name,
                item.restore_relative_path,
                item.data,
                item.metadata,
            )
            for item in result.payloads
        ),
        metadata_only=tuple(
            (item.state_class, item.metadata)
            for item in result.metadata_only
        ),
    )


@dataclass(frozen=True, slots=True)
class FullRecoveryExportPlan:
    schema_version: str
    source_deployment_identity_sha256: str
    status: str
    local_sources: tuple[str, ...]
    optional_missing: tuple[str, ...]
    required_adapters: tuple[str, ...]
    available_adapters: tuple[str, ...]
    blockers: tuple[str, ...]


def plan_full_recovery_export(
    *,
    target_root: str | Path,
    collection_spec: Mapping[str, Any],
    state_inventory: Mapping[str, Any],
    available_adapter_names: Sequence[str] = (),
) -> FullRecoveryExportPlan:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError(
            "non-production full recovery export planning may not target the live filesystem root"
        )
    manifest = FileDeploymentManifestProvider(
        root / "var/lib/jason/deployment-manifest.json"
    ).read()
    classes = _inventory_by_class(state_inventory)
    adapters = set(str(item) for item in available_adapter_names)

    local_sources: list[str] = []
    optional_missing: list[str] = []
    required_adapters: list[str] = []
    blockers: list[str] = []

    for raw in collection_spec["sources"]:
        source_id = str(raw["id"])
        state_class = str(raw["state_class"])
        strategy = str(raw["strategy"])
        required = bool(raw["required"])
        policy = classes.get(state_class)
        if policy is None:
            blockers.append("unknown_state_class:" + state_class)
            continue

        if strategy == "external_adapter":
            adapter = str(raw.get("adapter") or "")
            if required:
                required_adapters.append(adapter)
                if adapter not in adapters:
                    blockers.append("required_adapter_unavailable:" + adapter)
            elif adapter not in adapters:
                optional_missing.append(source_id)
            continue

        if strategy == "metadata_only":
            local_sources.append(source_id)
            continue

        source_relative = _safe_relative(
            str(raw.get("source_relative_path") or ""),
            label="source path",
        )
        source = root / source_relative
        if source.exists():
            local_sources.append(source_id)
        elif required:
            blockers.append("required_source_missing:" + source_id)
        else:
            optional_missing.append(source_id)

    return FullRecoveryExportPlan(
        schema_version="1.0",
        source_deployment_identity_sha256=str(manifest["identity_sha256"]),
        status="ready_for_export" if not blockers else "blocked",
        local_sources=tuple(sorted(local_sources)),
        optional_missing=tuple(sorted(optional_missing)),
        required_adapters=tuple(sorted(set(required_adapters))),
        available_adapters=tuple(sorted(adapters)),
        blockers=tuple(sorted(blockers)),
    )
