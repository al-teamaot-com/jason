from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator


INTERNAL_MANIFEST_MEMBER = "manifest/recovery-state.json"


class RecoveryRestoreError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RecoveryPayloadEntry:
    state_class: str
    member_name: str | None
    restore_relative_path: str | None
    sha256: str | None
    size_bytes: int
    source_metadata: Mapping[str, str | int | float | bool | None]


@dataclass(frozen=True, slots=True)
class RecoveryRestoreAction:
    action: str
    state_class: str
    member_name: str | None
    target: str | None
    contains_secrets: bool
    machine_bound: bool


@dataclass(frozen=True, slots=True)
class RecoveryRestorePlan:
    schema_version: str
    source_deployment_identity_sha256: str
    target_root: str
    status: str
    actions: tuple[RecoveryRestoreAction, ...]
    blockers: tuple[str, ...]
    destructive_restore_performed: bool = False


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative_path(value: str, *, label: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.strip():
        raise RecoveryRestoreError(f"unsafe {label}: {value!r}")
    return path.as_posix()


def build_payload_manifest(
    *,
    source_deployment_identity_sha256: str,
    entries: Sequence[RecoveryPayloadEntry],
) -> dict[str, Any]:
    source_id = source_deployment_identity_sha256.strip().lower()
    if len(source_id) != 64 or any(
        character not in "0123456789abcdef" for character in source_id
    ):
        raise RecoveryRestoreError("source deployment identity must be SHA-256 hex")

    normalized = []
    for entry in entries:
        if not entry.state_class.strip():
            raise RecoveryRestoreError("state_class must be non-empty")
        member_name = (
            None
            if entry.member_name is None
            else _safe_relative_path(entry.member_name, label="member name")
        )
        restore_path = (
            None
            if entry.restore_relative_path is None
            else _safe_relative_path(
                entry.restore_relative_path,
                label="restore path",
            )
        )
        if member_name is None:
            if entry.sha256 is not None or entry.size_bytes != 0:
                raise RecoveryRestoreError(
                    "metadata-only recovery entry may not carry payload digest/size"
                )
        else:
            if entry.sha256 is None or len(entry.sha256) != 64:
                raise RecoveryRestoreError(
                    "payload recovery entry requires a SHA-256 digest"
                )
            if restore_path is None:
                raise RecoveryRestoreError(
                    "payload recovery entry requires a restore path"
                )
        normalized.append(
            {
                "state_class": entry.state_class.strip(),
                "member_name": member_name,
                "restore_relative_path": restore_path,
                "sha256": entry.sha256,
                "size_bytes": int(entry.size_bytes),
                "source_metadata": dict(entry.source_metadata),
            }
        )

    return {
        "schema_version": "1.0",
        "source_deployment_identity_sha256": source_id,
        "entries": normalized,
    }


def assemble_recovery_members(
    *,
    source_deployment_identity_sha256: str,
    payloads: Sequence[
        tuple[
            str,
            str,
            str,
            bytes,
            Mapping[str, str | int | float | bool | None],
        ]
    ],
    metadata_only: Sequence[
        tuple[
            str,
            Mapping[str, str | int | float | bool | None],
        ]
    ] = (),
) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    entries: list[RecoveryPayloadEntry] = []

    for state_class, member_name, restore_path, data, metadata in payloads:
        safe_member = _safe_relative_path(member_name, label="member name")
        if safe_member == INTERNAL_MANIFEST_MEMBER:
            raise RecoveryRestoreError(
                "caller may not replace the internal recovery-state manifest"
            )
        if safe_member in members:
            raise RecoveryRestoreError(
                f"duplicate recovery payload member: {safe_member}"
            )
        payload = bytes(data)
        members[safe_member] = payload
        entries.append(
            RecoveryPayloadEntry(
                state_class=state_class,
                member_name=safe_member,
                restore_relative_path=_safe_relative_path(
                    restore_path,
                    label="restore path",
                ),
                sha256=_sha256(payload),
                size_bytes=len(payload),
                source_metadata=dict(metadata),
            )
        )

    for state_class, metadata in metadata_only:
        entries.append(
            RecoveryPayloadEntry(
                state_class=state_class,
                member_name=None,
                restore_relative_path=None,
                sha256=None,
                size_bytes=0,
                source_metadata=dict(metadata),
            )
        )

    manifest = build_payload_manifest(
        source_deployment_identity_sha256=source_deployment_identity_sha256,
        entries=entries,
    )
    members[INTERNAL_MANIFEST_MEMBER] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return members


def _validate_payload_manifest(
    manifest: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(manifest),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise RecoveryRestoreError(
            f"recovery payload manifest invalid at {location}: {first.message}"
        )


def _inventory_by_class(
    inventory: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    return {
        str(item["state_class"]): item
        for item in inventory.get("classes", ())
    }


def plan_recovery_restore(
    *,
    decrypted_members: Mapping[str, bytes],
    state_inventory: Mapping[str, Any],
    payload_manifest_schema: Mapping[str, Any],
    target_root: str | Path,
    expected_source_deployment_identity_sha256: str,
) -> RecoveryRestorePlan:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError(
            "recovery planning for the live filesystem root is not supported here"
        )
    if not root.is_absolute():
        raise RecoveryRestoreError("target_root must be absolute")

    raw_manifest = decrypted_members.get(INTERNAL_MANIFEST_MEMBER)
    if raw_manifest is None:
        raise RecoveryRestoreError("recovery-state manifest is missing from payload")
    try:
        manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecoveryRestoreError("recovery-state manifest is invalid JSON") from exc
    if not isinstance(manifest, Mapping):
        raise RecoveryRestoreError("recovery-state manifest must be an object")
    _validate_payload_manifest(
        manifest,
        schema=payload_manifest_schema,
    )

    source_id = str(
        manifest["source_deployment_identity_sha256"]
    ).strip().lower()
    expected_source = expected_source_deployment_identity_sha256.strip().lower()
    blockers: list[str] = []
    if source_id != expected_source:
        blockers.append("source_deployment_identity_mismatch")

    by_class = _inventory_by_class(state_inventory)
    actions: list[RecoveryRestoreAction] = []
    referenced_members = {INTERNAL_MANIFEST_MEMBER}

    for raw_entry in manifest["entries"]:
        state_class = str(raw_entry["state_class"])
        policy = by_class.get(state_class)
        if policy is None:
            blockers.append("unknown_state_class:" + state_class)
            continue

        recovery_action = str(policy["recovery_action"])
        full_export = bool(policy["full_recovery_export"])
        contains_secrets = bool(policy["contains_secrets"])
        machine_bound = bool(policy["machine_bound"])
        member_name = raw_entry["member_name"]
        restore_relative_path = raw_entry["restore_relative_path"]

        if member_name is not None:
            member_name = _safe_relative_path(
                str(member_name),
                label="member name",
            )
            referenced_members.add(member_name)
            if not full_export:
                blockers.append(
                    "state_class_not_exportable:" + state_class
                )
                continue
            payload = decrypted_members.get(member_name)
            if payload is None:
                blockers.append("payload_missing:" + member_name)
                continue
            if len(payload) != int(raw_entry["size_bytes"]):
                blockers.append("payload_size_mismatch:" + member_name)
                continue
            if _sha256(payload) != str(raw_entry["sha256"]):
                blockers.append("payload_digest_mismatch:" + member_name)
                continue

        if recovery_action == "restore":
            if member_name is None or restore_relative_path is None:
                blockers.append("restore_payload_missing:" + state_class)
                continue
            safe_restore = _safe_relative_path(
                str(restore_relative_path),
                label="restore path",
            )
            actions.append(
                RecoveryRestoreAction(
                    action="restore",
                    state_class=state_class,
                    member_name=member_name,
                    target=str(root / safe_restore),
                    contains_secrets=contains_secrets,
                    machine_bound=machine_bound,
                )
            )
        elif recovery_action == "reconstruct":
            if member_name is not None:
                blockers.append(
                    "reconstructable_state_should_not_be_payload:" + state_class
                )
                continue
            actions.append(
                RecoveryRestoreAction(
                    action="reconstruct",
                    state_class=state_class,
                    member_name=None,
                    target=None,
                    contains_secrets=contains_secrets,
                    machine_bound=machine_bound,
                )
            )
        elif recovery_action == "reenroll":
            if member_name is not None:
                blockers.append(
                    "machine_bound_state_should_not_be_payload:" + state_class
                )
                continue
            actions.append(
                RecoveryRestoreAction(
                    action="reenroll",
                    state_class=state_class,
                    member_name=None,
                    target=None,
                    contains_secrets=contains_secrets,
                    machine_bound=machine_bound,
                )
            )
            blockers.append("reenrollment_required:" + state_class)
        elif recovery_action == "discard":
            if member_name is not None:
                blockers.append(
                    "discarded_state_should_not_be_payload:" + state_class
                )
        else:
            blockers.append(
                "unsupported_recovery_action:"
                + state_class
                + ":"
                + recovery_action
            )

    unexpected = sorted(
        set(decrypted_members) - referenced_members
    )
    blockers.extend("unmanifested_payload:" + item for item in unexpected)

    if blockers:
        status = (
            "blocked_for_reenrollment"
            if all(item.startswith("reenrollment_required:") for item in blockers)
            else "blocked"
        )
    else:
        status = "ready_for_restore"

    return RecoveryRestorePlan(
        schema_version="1.0",
        source_deployment_identity_sha256=source_id,
        target_root=str(root),
        status=status,
        actions=tuple(actions),
        blockers=tuple(blockers),
        destructive_restore_performed=False,
    )


def apply_recovery_restore_plan(
    *,
    plan: RecoveryRestorePlan,
    decrypted_members: Mapping[str, bytes],
) -> dict[str, Any]:
    if plan.status != "ready_for_restore":
        raise PermissionError(
            "recovery restore plan is not ready: " + ",".join(plan.blockers)
        )
    root = Path(plan.target_root)
    if root == Path("/"):
        raise PermissionError("restore apply may not target the live filesystem root")

    restored: list[dict[str, Any]] = []
    for action in plan.actions:
        if action.action != "restore":
            continue
        if action.member_name is None or action.target is None:
            raise RecoveryRestoreError("restore action is missing payload/target")
        target = Path(action.target)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise RecoveryRestoreError("restore target escapes target root") from exc
        if target.exists() or target.is_symlink():
            raise RecoveryRestoreError(
                f"restore target already exists: {target}"
            )

        payload = decrypted_members.get(action.member_name)
        if payload is None:
            raise RecoveryRestoreError(
                f"restore payload disappeared: {action.member_name}"
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=target.parent,
            prefix=".jason-restore-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
        restored.append(
            {
                "state_class": action.state_class,
                "target": str(target),
                "contains_secrets": action.contains_secrets,
                "sha256": _sha256(payload),
            }
        )

    return {
        "status": "restore_payload_applied",
        "target_root": str(root),
        "restored": restored,
        "reconstruct_actions": [
            asdict(action)
            for action in plan.actions
            if action.action == "reconstruct"
        ],
        "services_started": False,
        "migrations_run": False,
        "provider_reenrollment_performed": False,
    }


def acknowledge_reenrollment(
    *,
    plan: RecoveryRestorePlan,
    completed_state_classes: Sequence[str],
) -> RecoveryRestorePlan:
    completed = {str(item).strip() for item in completed_state_classes if str(item).strip()}
    if not completed:
        raise RecoveryRestoreError("at least one completed re-enrollment state class is required")

    expected = {
        blocker.split(":", 1)[1]
        for blocker in plan.blockers
        if blocker.startswith("reenrollment_required:")
    }
    unknown = completed - expected
    if unknown:
        raise RecoveryRestoreError(
            "re-enrollment completion references state classes not required by the plan: "
            + ",".join(sorted(unknown))
        )

    remaining_blockers = tuple(
        blocker
        for blocker in plan.blockers
        if not (
            blocker.startswith("reenrollment_required:")
            and blocker.split(":", 1)[1] in completed
        )
    )
    remaining_actions = tuple(
        action
        for action in plan.actions
        if not (
            action.action == "reenroll"
            and action.state_class in completed
        )
    )
    return RecoveryRestorePlan(
        schema_version=plan.schema_version,
        source_deployment_identity_sha256=plan.source_deployment_identity_sha256,
        target_root=plan.target_root,
        status="ready_for_restore" if not remaining_blockers else "blocked",
        actions=remaining_actions,
        blockers=remaining_blockers,
        destructive_restore_performed=plan.destructive_restore_performed,
    )
