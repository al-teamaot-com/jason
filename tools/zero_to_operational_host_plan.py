from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import stat
import tarfile
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)
from jsonschema import Draft202012Validator

from bootstrap.candidate_host import load_candidate_host_identity
from bootstrap.candidate_host_preflight import preflight_candidate_host
from bootstrap.candidate_openbao_restore import (
    build_candidate_openbao_restore_plan,
)
from bootstrap.candidate_runtime import (
    load_candidate_runtime_config,
    validate_candidate_runtime_environment_file,
)
from bootstrap.candidate_mcp import (
    load_candidate_mcp_config,
    validate_candidate_mcp_environment,
)
from bootstrap.clean_install import read_json, validate_json_document
from bootstrap.secret_requirements import (
    build_secret_requirements,
    load_secret_presence_attestation,
)


class HostAcceptancePlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HostAcceptancePlanResult:
    schema_version: str
    scenario_id: str
    status: str
    instance_id: str
    clean_host: bool
    enabled_providers: tuple[str, ...]
    required_secret_references: tuple[str, ...]
    current_release_sha256: str | None
    next_release_sha256: str | None
    recovery_keys_valid: bool
    openbao_recovery_valid: bool
    runtime_environment_valid: bool
    mcp_environment_valid: bool
    ollama_model: str | None
    second_clean_environment_required: bool
    production_authorized: bool
    blockers: tuple[str, ...]


def _validate_plan_schema(
    plan: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(plan),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise HostAcceptancePlanError(
            f"host acceptance plan invalid at {location}: {first.message}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(path: Path, *, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise HostAcceptancePlanError(f"{label} is unavailable: {path}")


def _private_file(path: Path, *, label: str) -> None:
    _regular_file(path, label=label)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise HostAcceptancePlanError(
            f"{label} permissions are too broad: {oct(mode)}"
        )


def _validate_release(
    release: Mapping[str, Any],
    *,
    label: str,
) -> str:
    archive = Path(str(release["archive"]))
    _regular_file(archive, label=f"{label} release archive")
    observed = _sha256(archive)
    expected = str(release["sha256"]).lower()
    if observed != expected:
        raise HostAcceptancePlanError(
            f"{label} release artifact SHA-256 mismatch"
        )
    try:
        with tarfile.open(archive, "r:*") as handle:
            for member in handle.getmembers():
                path = Path(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or member.issym()
                    or member.islnk()
                    or member.isdev()
                ):
                    raise HostAcceptancePlanError(
                        f"{label} release archive contains unsafe member: {member.name}"
                    )
    except tarfile.TarError as exc:
        raise HostAcceptancePlanError(
            f"{label} release archive is invalid"
        ) from exc
    return observed


def _validate_recovery_keys(
    *,
    recipient_public_path: Path,
    signer_private_path: Path,
) -> None:
    _regular_file(
        recipient_public_path,
        label="recovery recipient public key",
    )
    _private_file(
        signer_private_path,
        label="recovery signer private key",
    )
    public = load_pem_public_key(recipient_public_path.read_bytes())
    private = load_pem_private_key(
        signer_private_path.read_bytes(),
        password=None,
    )
    if not isinstance(public, X25519PublicKey):
        raise HostAcceptancePlanError(
            "recovery recipient public key must be X25519"
        )
    if not isinstance(private, Ed25519PrivateKey):
        raise HostAcceptancePlanError(
            "recovery signer private key must be Ed25519"
        )


def _expected_candidate_mount_sources(
    target_root: str | Path,
) -> dict[str, str]:
    root = Path(target_root)
    base = root / "opt/jason/bootstrap/secrets/openbao"
    return {
        "JASON_OPENBAO_ROLE_ID_HOST_PATH": str(
            base / "datto-rmm-read-approle/role-id"
        ),
        "JASON_OPENBAO_SECRET_ID_HOST_PATH": str(
            base / "datto-rmm-read-approle/secret-id"
        ),
        "JASON_AUTOTASK_OPENBAO_ROLE_ID_HOST_PATH": str(
            base / "autotask-read-approle/role-id"
        ),
        "JASON_AUTOTASK_OPENBAO_SECRET_ID_HOST_PATH": str(
            base / "autotask-read-approle/secret-id"
        ),
    }


def preflight_host_acceptance_plan(
    *,
    plan_path: str | Path,
    repository_root: str | Path,
    target_root: str | Path = "/",
    host=None,
    effective_uid: int | None = None,
) -> HostAcceptancePlanResult:
    repo = Path(repository_root)
    plan = read_json(plan_path)
    schema = read_json(
        repo / "config/schemas/zero-to-operational-host-plan.schema.json"
    )
    if not isinstance(plan, Mapping):
        raise HostAcceptancePlanError("host acceptance plan must be an object")
    _validate_plan_schema(plan, schema)

    blockers: list[str] = []
    host_preflight = preflight_candidate_host(
        root=target_root,
        identity_path=str(plan["candidate_host_identity"]),
        host=host,
        effective_uid=effective_uid,
    )
    blockers.extend("host:" + item for item in host_preflight.blockers)
    candidate_identity = None
    try:
        candidate_identity = load_candidate_host_identity(
            str(plan["candidate_host_identity"])
        )
    except Exception as exc:
        blockers.append("candidate_host_identity:" + str(exc))

    current_digest: str | None = None
    next_digest: str | None = None
    try:
        current_digest = _validate_release(
            dict(plan["current_release"]),
            label="current",
        )
    except HostAcceptancePlanError as exc:
        blockers.append("current_release:" + str(exc))
    try:
        next_digest = _validate_release(
            dict(plan["next_release"]),
            label="next",
        )
    except HostAcceptancePlanError as exc:
        blockers.append("next_release:" + str(exc))

    msp_configuration = read_json(str(plan["msp_configuration"]))
    msp_policy = read_json(str(plan["msp_policy"]))
    try:
        validate_json_document(
            document=msp_configuration,
            schema=read_json(
                repo / "config/schemas/msp-configuration.schema.json"
            ),
            label="MSP configuration",
        )
    except Exception as exc:
        blockers.append("msp_configuration:" + str(exc))
    try:
        validate_json_document(
            document=msp_policy,
            schema=read_json(
                repo / "config/schemas/msp-policy.schema.json"
            ),
            label="MSP policy",
        )
    except Exception as exc:
        blockers.append("msp_policy:" + str(exc))

    enabled_providers = tuple(
        sorted(
            str(provider_id)
            for provider_id, raw in dict(
                msp_configuration.get("providers") or {}
            ).items()
            if bool(dict(raw or {}).get("enabled"))
        )
    )
    configured_canaries = tuple(
        sorted(str(item) for item in plan["provider_canary"]["required_providers"])
    )
    if configured_canaries != enabled_providers:
        blockers.append(
            "provider_canary_set_mismatch:"
            + ",".join(configured_canaries)
            + "!="
            + ",".join(enabled_providers)
        )

    openbao_recovery_valid = False
    if candidate_identity is not None:
        try:
            recovery = dict(plan["openbao_recovery"])
            build_candidate_openbao_restore_plan(
                target_root=target_root,
                candidate_identity=candidate_identity,
                snapshot_path=recovery["snapshot"],
                snapshot_checksum_path=recovery["checksum"],
                init_path=recovery["init_file"],
                approle_root=recovery["approle_root"],
                provider_ids=enabled_providers,
            )
            openbao_recovery_valid = True
        except Exception as exc:
            blockers.append("openbao_recovery:" + str(exc))

    requirements = build_secret_requirements(msp_configuration)
    required_secret_references = tuple(
        sorted(item.secret_reference for item in requirements if item.required)
    )
    try:
        available = set(
            load_secret_presence_attestation(
                str(plan["secret_presence_attestation"])
            )
        )
    except Exception as exc:
        blockers.append("secret_presence_attestation:" + str(exc))
    else:
        missing = sorted(set(required_secret_references) - available)
        blockers.extend("secret_reference_missing:" + item for item in missing)

    runtime_environment_valid = False
    ollama_model: str | None = None
    try:
        runtime_config = load_candidate_runtime_config(
            repo / "config/candidate-runtime.v1.json",
            repo / "config/schemas/candidate-runtime.schema.json",
        )
        runtime_summary = validate_candidate_runtime_environment_file(
            env_file=str(plan["candidate_runtime_env"]),
            runtime_config=runtime_config,
            require_mount_sources=False,
        )
        ollama_model = str(runtime_summary["ollama_model"])
        expected_mounts = _expected_candidate_mount_sources(target_root)
        if runtime_summary["mount_sources"] != expected_mounts:
            raise HostAcceptancePlanError(
                "candidate runtime credential paths do not match "
                "the canonical OpenBao restore outputs"
            )
        runtime_environment_valid = True
    except Exception as exc:
        blockers.append("candidate_runtime_env:" + str(exc))

    mcp_environment_valid = False
    if runtime_environment_valid:
        try:
            mcp_config = load_candidate_mcp_config(
                repo / "config/candidate-mcp.v1.json",
                repo / "config/schemas/candidate-mcp.schema.json",
            )
            validate_candidate_mcp_environment(
                env_file=str(plan["candidate_runtime_env"]),
                runtime_config=runtime_config,
                mcp_config=mcp_config,
                require_mount_sources=False,
            )
            mcp_environment_valid = True
        except Exception as exc:
            blockers.append("candidate_mcp_env:" + str(exc))

    recovery_keys_valid = False
    try:
        _validate_recovery_keys(
            recipient_public_path=Path(
                str(plan["recovery_recipient_public_key"])
            ),
            signer_private_path=Path(
                str(plan["recovery_signer_private_key"])
            ),
        )
    except Exception as exc:
        blockers.append("recovery_keys:" + str(exc))
    else:
        recovery_keys_valid = True

    current_source = str(plan["current_release"]["source_sha"])
    next_source = str(plan["next_release"]["source_sha"])
    if current_source == next_source:
        blockers.append("next_release_source_sha_must_differ")

    if plan.get("production_authorized") is not False:
        blockers.append("production_authorization_must_be_false")
    if plan.get("second_clean_environment_required") is not True:
        blockers.append("second_clean_environment_must_be_required")

    return HostAcceptancePlanResult(
        schema_version="1.0",
        scenario_id=str(plan["scenario_id"]),
        status="ready_for_host_acceptance" if not blockers else "blocked",
        instance_id=host_preflight.instance_id,
        clean_host=host_preflight.clean_host,
        enabled_providers=enabled_providers,
        required_secret_references=required_secret_references,
        current_release_sha256=current_digest,
        next_release_sha256=next_digest,
        recovery_keys_valid=recovery_keys_valid,
        openbao_recovery_valid=openbao_recovery_valid,
        runtime_environment_valid=runtime_environment_valid,
        mcp_environment_valid=mcp_environment_valid,
        ollama_model=ollama_model,
        second_clean_environment_required=True,
        production_authorized=False,
        blockers=tuple(blockers),
    )


def result_json(result: HostAcceptancePlanResult) -> str:
    return json.dumps(asdict(result), indent=2, sort_keys=True) + "\n"
