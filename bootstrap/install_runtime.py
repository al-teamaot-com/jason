from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import re
import tempfile
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
)

from kernel.identity_authority.durable import SQLiteIdentityAuthorityStore
from kernel.client_boundaries.sqlite import SQLiteClientBoundaryStore
from orchestrator.event_store import SQLiteOrchestrationEventStore
from orchestrator.approval_continuation_guard import SQLiteApprovalContinuationGuard


class BootstrapRuntimeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseStageResult:
    source_sha: str
    artifact_sha256: str
    release_path: str
    current_link: str


@dataclass(frozen=True, slots=True)
class StateStoreResult:
    store_id: str
    relative_path: str
    initialization: str
    status: str


@dataclass(frozen=True, slots=True)
class ServiceStageResult:
    source: str
    target: str
    status: str


def load_resources(
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
        first = errors[0]
        raise BootstrapRuntimeError(
            "bootstrap resource inventory invalid: " + first.message
        )
    return document


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        path = Path(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise BootstrapRuntimeError(
                f"release archive contains unsafe path: {member.name}"
            )
        if member.issym() or member.islnk() or member.isdev():
            raise BootstrapRuntimeError(
                f"release archive contains unsupported member type: {member.name}"
            )
    return members


def stage_release_archive(
    *,
    archive_path: str | Path,
    expected_artifact_sha256: str,
    source_sha: str,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity | None = None,
) -> ReleaseStageResult:
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="release staging",
    )

    expected = expected_artifact_sha256.strip().lower()
    observed = file_sha256(archive_path)
    if observed != expected:
        raise BootstrapRuntimeError("release artifact SHA-256 mismatch")
    normalized_source = source_sha.strip().lower()
    if len(normalized_source) != 40 or any(
        character not in "0123456789abcdef" for character in normalized_source
    ):
        raise BootstrapRuntimeError("source_sha must be 40 hexadecimal characters")

    releases = root / "opt/jason/releases"
    releases.mkdir(parents=True, exist_ok=True)
    final = releases / normalized_source
    if final.exists():
        raise BootstrapRuntimeError("release destination already exists")

    staging = releases / (".staging-" + normalized_source)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            members = _safe_archive_members(archive)
            archive.extractall(staging, members=members, filter="data")
        os.replace(staging, final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    current = root / "opt/jason/current"
    current.parent.mkdir(parents=True, exist_ok=True)
    temporary_link = current.with_name(".current.new")
    if temporary_link.exists() or temporary_link.is_symlink():
        temporary_link.unlink()
    temporary_link.symlink_to(Path("releases") / normalized_source)
    os.replace(temporary_link, current)

    return ReleaseStageResult(
        source_sha=normalized_source,
        artifact_sha256=observed,
        release_path=str(final),
        current_link=str(current),
    )


def initialize_state_stores(
    *,
    target_root: str | Path,
    resources: Mapping[str, Any],
    candidate_identity: CandidateHostIdentity | None = None,
) -> tuple[StateStoreResult, ...]:
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="state initialization",
    )

    results: list[StateStoreResult] = []
    for store in resources["state_stores"]:
        relative = str(store["relative_path"])
        path = root / relative
        strategy = str(store["initialization"])
        store_id = str(store["id"])

        if strategy == "bootstrap_explicit":
            path.parent.mkdir(parents=True, exist_ok=True)
            if store_id == "identity-authority":
                handle = SQLiteIdentityAuthorityStore(path)
                handle.close()
            elif store_id == "client-boundaries":
                handle = SQLiteClientBoundaryStore(path)
                handle.close()
            elif store_id == "orchestration-events":
                handle = SQLiteOrchestrationEventStore(path)
                handle._connection.close()
            elif store_id == "approval-continuations":
                SQLiteApprovalContinuationGuard(str(path)).initialize()
            else:
                raise BootstrapRuntimeError(
                    f"no explicit initializer registered for {store_id}"
                )
            os.chmod(path, 0o600)
            status = "initialized"
        elif strategy == "runtime_owned":
            path.parent.mkdir(parents=True, exist_ok=True)
            status = "deferred_to_runtime_owner"
        elif strategy == "external_database":
            path.parent.mkdir(parents=True, exist_ok=True)
            status = "external_initialization_required"
        else:
            raise BootstrapRuntimeError(
                f"unsupported state initialization strategy: {strategy}"
            )

        results.append(
            StateStoreResult(
                store_id=store_id,
                relative_path=relative,
                initialization=strategy,
                status=status,
            )
        )
    return tuple(results)


_PROHIBITED_UNIT_FRAGMENTS = (
    "/home/al",
    "/home/",
    "/root/",
)


def stage_portable_systemd_units(
    *,
    repository_root: str | Path,
    target_root: str | Path,
    resources: Mapping[str, Any],
    candidate_identity: CandidateHostIdentity | None = None,
) -> tuple[ServiceStageResult, ...]:
    repo = Path(repository_root)
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="systemd staging",
    )
    target_dir = root / "etc/systemd/system"
    target_dir.mkdir(parents=True, exist_ok=True)

    results: list[ServiceStageResult] = []
    for unit in resources["systemd_units"]:
        source_relative = str(unit["source"])
        source = repo / source_relative
        if not bool(unit["portable"]):
            results.append(
                ServiceStageResult(
                    source=source_relative,
                    target="",
                    status="blocked_nonportable",
                )
            )
            continue
        text = source.read_text(encoding="utf-8")
        bad = next(
            (fragment for fragment in _PROHIBITED_UNIT_FRAGMENTS if fragment in text),
            None,
        )
        if bad is not None:
            raise BootstrapRuntimeError(
                f"portable unit unexpectedly contains prohibited host path {bad}: "
                f"{source_relative}"
            )
        target = target_dir / source.name
        target.write_text(text, encoding="utf-8")
        results.append(
            ServiceStageResult(
                source=source_relative,
                target=str(target),
                status="staged",
            )
        )
    return tuple(results)


def write_bootstrap_runtime_manifest(
    *,
    target_root: str | Path,
    release: ReleaseStageResult,
    state: tuple[StateStoreResult, ...],
    services: tuple[ServiceStageResult, ...],
    resources: Mapping[str, Any],
) -> Path:
    root = Path(target_root)
    output = root / "var/lib/jason/bootstrap-runtime.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "release": asdict(release),
        "state_stores": [asdict(item) for item in state],
        "systemd_units": [asdict(item) for item in services],
        "networks": list(resources["networks"]),
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def evaluate_candidate_readiness(
    *,
    target_root: str | Path,
    resources: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(target_root)
    blockers: list[str] = []
    checks: dict[str, str] = {}

    current = root / "opt/jason/current"
    if not current.is_symlink() or not current.exists():
        blockers.append("release_current_link_missing")
        checks["release"] = "fail"
    else:
        checks["release"] = "pass"

    runtime_manifest = root / "var/lib/jason/bootstrap-runtime.json"
    if not runtime_manifest.is_file():
        blockers.append("bootstrap_runtime_manifest_missing")
        checks["bootstrap_runtime_manifest"] = "fail"
    else:
        checks["bootstrap_runtime_manifest"] = "pass"

    for store in resources["state_stores"]:
        if store["initialization"] != "bootstrap_explicit":
            continue
        path = root / str(store["relative_path"])
        if not path.is_file():
            blockers.append("state_store_missing:" + str(store["id"]))

    staged_units = root / "etc/systemd/system"
    for unit in resources["systemd_units"]:
        if not unit["portable"]:
            continue
        name = Path(str(unit["source"])).name
        unit_path = staged_units / name
        if not unit_path.is_file():
            blockers.append("portable_unit_missing:" + name)
            continue
        unit_text = unit_path.read_text(encoding="utf-8")
        for line in unit_text.splitlines():
            if not line.startswith("ExecStart="):
                continue
            for absolute in re.findall(r"(?<![A-Za-z0-9_])(/opt/jason/current/[^ ]+)", line):
                relative = absolute.removeprefix("/")
                if not (root / relative).is_file():
                    blockers.append(
                        "release_service_target_missing:" + absolute
                    )

    required_networks = [
        item["name"] for item in resources["networks"] if item["required"]
    ]
    checks["required_networks"] = ",".join(required_networks)

    return {
        "status": "ready_for_runtime_activation" if not blockers else "blocked",
        "checks": checks,
        "blockers": blockers,
        "network_activation_required": required_networks,
        "service_activation_performed": False,
        "provider_secret_enrollment_performed": False,
    }
