"""Owner-governed durable playbook-autonomy promotion admin.

This module is intentionally provider-neutral. It can only promote a playbook
that is already registered as production, enabled, and autonomy.activation=
"autonomous" in the source-controlled playbook registry. The durable promotion
record remains separate from source metadata.

The CLI exists for bounded operational recovery when the MCP tool catalog has
not refreshed yet. It verifies the configured owner identity, validates the
exact registry scope, writes the same durable approval store consumed by the
runtime, and appends a local audit record. It does not call any provider.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from autonomous_remediation.playbook_autonomy_approval import (
    PlaybookAutonomyApproval,
    SQLitePlaybookAutonomyApprovalStore,
)
from jason_runtime.datto_component_approval_registry import approval_owner_identities


class AutonomyPromotionAdminError(RuntimeError):
    pass


def _registry_entry(
    *, registry_path: Path, playbook_id: str
) -> tuple[Mapping[str, Any], str]:
    raw_bytes = registry_path.read_bytes()
    fingerprint = hashlib.sha256(raw_bytes).hexdigest()
    document = json.loads(raw_bytes.decode("utf-8"))
    playbooks = document.get("playbooks")
    if not isinstance(playbooks, list):
        raise AutonomyPromotionAdminError("PLAYBOOK_REGISTRY_INVALID")

    matches = [
        item
        for item in playbooks
        if isinstance(item, Mapping)
        and str(item.get("id") or "").strip() == playbook_id
    ]
    if len(matches) != 1:
        raise AutonomyPromotionAdminError("PLAYBOOK_REGISTRY_EXACT_MATCH_REQUIRED")
    return matches[0], fingerprint


def registered_autonomy_scope(
    *, registry_path: Path, playbook_id: str
) -> dict[str, Any]:
    entry, registry_fingerprint = _registry_entry(
        registry_path=registry_path, playbook_id=playbook_id
    )
    if str(entry.get("lifecycle") or "").strip().casefold() != "production":
        raise AutonomyPromotionAdminError("PLAYBOOK_NOT_PRODUCTION")
    if entry.get("enabled") is not True:
        raise AutonomyPromotionAdminError("PLAYBOOK_NOT_ENABLED")

    autonomy = entry.get("autonomy")
    if not isinstance(autonomy, Mapping):
        raise AutonomyPromotionAdminError("PLAYBOOK_AUTONOMY_METADATA_REQUIRED")
    if str(autonomy.get("activation") or "").strip().casefold() != "autonomous":
        raise AutonomyPromotionAdminError("PLAYBOOK_AUTONOMY_NOT_ACTIVATED")

    version = str(entry.get("version") or "").strip()
    policy_id = str(autonomy.get("policy_id") or "").strip()
    capabilities = autonomy.get("allowed_capabilities")
    if not version or not policy_id:
        raise AutonomyPromotionAdminError("PLAYBOOK_AUTONOMY_SCOPE_INCOMPLETE")
    if not isinstance(capabilities, list) or not capabilities:
        raise AutonomyPromotionAdminError("PLAYBOOK_AUTONOMY_CAPABILITIES_REQUIRED")

    normalized = tuple(str(item).strip() for item in capabilities)
    if any(
        not item or any(token in item for token in ("*", "?", "[", "]"))
        for item in normalized
    ):
        raise AutonomyPromotionAdminError("PLAYBOOK_AUTONOMY_EXACT_CAPABILITIES_REQUIRED")
    if len(set(normalized)) != len(normalized):
        raise AutonomyPromotionAdminError("PLAYBOOK_AUTONOMY_CAPABILITIES_DUPLICATE")

    return {
        "playbook_id": playbook_id,
        "playbook_version": version,
        "policy_id": policy_id,
        "allowed_capabilities": normalized,
        "registry_sha256": registry_fingerprint,
    }


def promote_registered_playbook(
    *,
    store: SQLitePlaybookAutonomyApprovalStore,
    registry_path: Path,
    playbook_id: str,
    approved_by: str,
) -> tuple[PlaybookAutonomyApproval, bool, dict[str, Any]]:
    actor = str(approved_by or "").strip()
    owners = approval_owner_identities()
    if not owners or actor not in owners:
        raise AutonomyPromotionAdminError("PLAYBOOK_AUTONOMY_OWNER_REQUIRED")

    scope = registered_autonomy_scope(
        registry_path=registry_path, playbook_id=str(playbook_id or "").strip()
    )
    existing = store.find_scope_approved(
        playbook_id=scope["playbook_id"],
        playbook_version=scope["playbook_version"],
        policy_id=scope["policy_id"],
        required_capabilities=scope["allowed_capabilities"],
    )
    if existing is not None:
        return existing, False, scope

    record = store.new(
        playbook_id=scope["playbook_id"],
        playbook_version=scope["playbook_version"],
        policy_id=scope["policy_id"],
        allowed_capabilities=scope["allowed_capabilities"],
        approved_by=actor,
        expires_at=None,
    )
    store.put(record)
    return record, True, scope


def append_admin_audit(
    *,
    audit_path: Path,
    actor: str,
    record: PlaybookAutonomyApproval,
    created: bool,
    scope: Mapping[str, Any],
) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "playbook.autonomy.promoted" if created else "playbook.autonomy.promotion.reused",
        "approved_by": actor,
        "approval_id": record.approval_id,
        "playbook_id": record.playbook_id,
        "playbook_version": record.playbook_version,
        "policy_id": record.policy_id,
        "allowed_capabilities": list(record.allowed_capabilities),
        "registry_sha256": scope["registry_sha256"],
        "status": record.status,
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("playbook_id")
    parser.add_argument("--approved-by", required=True)
    parser.add_argument(
        "--store",
        default="/var/lib/jason/openclaw/playbook-autonomy.sqlite3",
    )
    parser.add_argument(
        "--registry",
        default="/app/implementation/autonomous_remediation/playbook_registry.json",
    )
    parser.add_argument(
        "--audit",
        default="/var/lib/jason/openclaw/autonomy-promotion-admin.jsonl",
    )
    args = parser.parse_args()

    store = SQLitePlaybookAutonomyApprovalStore(args.store)
    try:
        record, created, scope = promote_registered_playbook(
            store=store,
            registry_path=Path(args.registry),
            playbook_id=args.playbook_id,
            approved_by=args.approved_by,
        )
        append_admin_audit(
            audit_path=Path(args.audit),
            actor=args.approved_by,
            record=record,
            created=created,
            scope=scope,
        )
        print(json.dumps({
            "status": "succeeded",
            "created": created,
            "approval_id": record.approval_id,
            "playbook_id": record.playbook_id,
            "playbook_version": record.playbook_version,
            "policy_id": record.policy_id,
            "allowed_capabilities": list(record.allowed_capabilities),
            "registry_sha256": scope["registry_sha256"],
        }, sort_keys=True))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
