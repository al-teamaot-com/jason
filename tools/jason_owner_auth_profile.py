"""Immutable source-gated profile for Jason Owner approval (not Entra administration).

This source declaration has no ability to grant rights itself. The native
release manager must separately authorize and deploy an exact release SHA.
"""
from __future__ import annotations
import json
from pathlib import Path

POLICY = "config/jason-owner-authorization-profile.json"
EXPECTED = {
    "schema_version": "1.0",
    "policy_id": "aot-jason-owner-exact-entra-v1",
    "organization_id": "aot",
    "microsoft_tenant_id": "f7054323-d52b-4863-8c2f-1898f0b6077c",
    "jason_owner_object_id": "bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
    "jason_owner_identity": "person-entra-bee80bdcffb04c50b453c09d4d411f5f",
    "microsoft_admin_object_id": "c848022d-e13b-4457-84b0-e2f5c00dcaf6",
    "microsoft_admin_jason_owner_authority": False,
    "provider_execution_uses_jason_service_identity": True,
    "preserve_production_freeze": True,
    "approval_per_exact_action": True,
}


def declared_jason_owner_profile(source_tree: Path) -> str:
    path = Path(source_tree) / POLICY
    if not path.exists():
        # Pre-profile historic release trees and isolated minimal fixtures have
        # no entitlement to the new Owner role. Absence means disabled.
        return ""
    if not path.is_file() or path.is_symlink():
        raise ValueError("JASON_OWNER_SOURCE_POLICY_INVALID_PATH")
    if path.stat().st_size > 4096:
        raise ValueError("JASON_OWNER_SOURCE_POLICY_OVERSIZE")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("JASON_OWNER_SOURCE_POLICY_INVALID") from exc
    if not isinstance(payload, dict) or set(payload) != set(EXPECTED) | {"enabled"}:
        raise ValueError("JASON_OWNER_SOURCE_POLICY_SCHEMA_INVALID")
    if not isinstance(payload.get("enabled"), bool):
        raise ValueError("JASON_OWNER_SOURCE_POLICY_ENABLED_INVALID")
    if any(type(payload[k]) is not type(v) or payload[k] != v for k, v in EXPECTED.items()):
        raise ValueError("JASON_OWNER_SOURCE_POLICY_BINDING_MISMATCH")
    return "jason-owner-v1" if payload["enabled"] else ""
