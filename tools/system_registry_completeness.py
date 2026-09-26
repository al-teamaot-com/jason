#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "implementation/kernel/system_registry/production-registry.json"

_OPERATIONAL_LIFECYCLES = {"configured", "verified", "active"}


@dataclass(frozen=True)
class CompletenessResult:
    missing_capabilities: tuple[str, ...]
    missing_providers: tuple[str, ...]
    missing_identity_bindings: tuple[str, ...]
    missing_credential_profiles: tuple[str, ...]
    missing_components: tuple[str, ...]
    stale_components: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.missing_capabilities
            or self.missing_providers
            or self.missing_identity_bindings
            or self.missing_credential_profiles
            or self.missing_components
            or self.stale_components
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "pass" if self.passed else "fail",
            "missing_capabilities": list(self.missing_capabilities),
            "missing_providers": list(self.missing_providers),
            "missing_identity_bindings": list(self.missing_identity_bindings),
            "missing_credential_profiles": list(self.missing_credential_profiles),
            "missing_components": list(self.missing_components),
            "stale_components": list(self.stale_components),
            "summary": {
                "missing_capability_count": len(self.missing_capabilities),
                "missing_provider_count": len(self.missing_providers),
                "missing_identity_binding_count": len(self.missing_identity_bindings),
                "missing_credential_profile_count": len(self.missing_credential_profiles),
                "missing_component_count": len(self.missing_components),
                "stale_component_count": len(self.stale_components),
            },
        }


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _registered_capability_names(manifest: dict[str, object]) -> set[str]:
    names: set[str] = set()
    for entity in manifest.get("entities", []):
        if not isinstance(entity, dict) or entity.get("entity_type") != "capability":
            continue
        declared = entity.get("declared_state")
        if not isinstance(declared, dict):
            continue
        name = str(declared.get("capability_name") or "").strip()
        if name:
            names.add(name)
    return names


def _registered_provider_ids(manifest: dict[str, object]) -> set[str]:
    ids: set[str] = set()
    for entity in manifest.get("entities", []):
        if not isinstance(entity, dict) or entity.get("entity_type") != "provider":
            continue
        declared = entity.get("declared_state")
        if not isinstance(declared, dict):
            continue
        provider_id = str(declared.get("provider_id") or "").strip()
        if not provider_id:
            provider_id = str(entity.get("registry_id") or "").removeprefix("provider.").strip()
        if provider_id:
            ids.add(provider_id)
    return ids


def _binding_key(*, tenant_id: object, object_id: object, principal_id: object) -> str:
    tenant = str(tenant_id or "").strip()
    obj = str(object_id or "").strip()
    principal = str(principal_id or "").strip()
    if not tenant or not obj or not principal:
        return ""
    return f"{tenant}|{obj}|{principal}"


def _registered_identity_bindings(manifest: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for entity in manifest.get("entities", []):
        if not isinstance(entity, dict) or entity.get("entity_type") != "identity_binding":
            continue
        declared = entity.get("declared_state")
        if not isinstance(declared, dict):
            continue
        key = _binding_key(
            tenant_id=declared.get("tenant_id"),
            object_id=declared.get("object_id"),
            principal_id=declared.get("principal_id"),
        )
        if key:
            keys.add(key)
    return keys


def _registered_credential_profiles(manifest: dict[str, object]) -> set[str]:
    profiles: set[str] = set()
    for entity in manifest.get("entities", []):
        if not isinstance(entity, dict) or entity.get("entity_type") != "credential_reference":
            continue
        declared = entity.get("declared_state")
        if not isinstance(declared, dict):
            continue
        profile = str(declared.get("app_role_profile") or "").strip()
        if profile:
            profiles.add(profile)
    return profiles


def _registered_operational_containers(manifest: dict[str, object]) -> set[str]:
    names: set[str] = set()
    for entity in manifest.get("entities", []):
        if not isinstance(entity, dict) or entity.get("entity_type") != "component":
            continue
        if str(entity.get("lifecycle_status") or "") not in _OPERATIONAL_LIFECYCLES:
            continue
        declared = entity.get("declared_state")
        if not isinstance(declared, dict):
            continue
        name = str(declared.get("container_name") or "").strip()
        if name:
            names.add(name)
    return names


def _active_capability_names(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        raise ValueError("capability payload must be a JSON object")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("capability payload must contain capabilities[]")
    names: set[str] = set()
    for item in capabilities:
        if not isinstance(item, dict):
            continue
        if str(item.get("lifecycle") or "").casefold() != "active":
            continue
        name = str(item.get("capability") or "").strip()
        if name:
            names.add(name)
    return names


def _live_provider_ids(payload: object) -> set[str]:
    rows = payload.get("providers") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("provider payload must be a JSON array or object with providers[]")
    ids: set[str] = set()
    for item in rows:
        if isinstance(item, str):
            provider_id = item.strip()
        elif isinstance(item, dict):
            provider_id = str(item.get("provider_id") or "").strip()
        else:
            continue
        if provider_id:
            ids.add(provider_id)
    return ids


def _live_identity_bindings(payload: object) -> set[str]:
    rows = payload.get("identity_bindings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(
            "identity-binding payload must be a JSON array or object with identity_bindings[]"
        )
    keys: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "active").casefold() != "active":
            continue
        key = _binding_key(
            tenant_id=item.get("tenant_id"),
            object_id=item.get("object_id"),
            principal_id=item.get("principal_id"),
        )
        if key:
            keys.add(key)
    return keys


def _live_credential_profiles(payload: object) -> set[str]:
    rows = payload.get("credential_profiles") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError(
            "credential-profile payload must be a JSON array or object with credential_profiles[]"
        )
    profiles: set[str] = set()
    for item in rows:
        if isinstance(item, str):
            profile = item.strip()
        elif isinstance(item, dict):
            profile = str(item.get("profile") or "").strip()
        else:
            continue
        if profile:
            profiles.add(profile)
    return profiles


def _live_container_names(payload: object) -> set[str]:
    if isinstance(payload, dict):
        rows = payload.get("containers")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError("container payload must be a JSON array or object with containers[]")
    names: set[str] = set()
    for item in rows:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("Names") or "").strip()
        else:
            continue
        if name:
            names.add(name)
    return names


def audit(
    *,
    manifest: dict[str, object],
    capability_payload: object,
    provider_payload: object,
    identity_binding_payload: object,
    credential_profile_payload: object,
    container_payload: object,
    ignored_live_containers: Iterable[str] = (),
) -> CompletenessResult:
    registered_caps = _registered_capability_names(manifest)
    active_caps = _active_capability_names(capability_payload)
    registered_providers = _registered_provider_ids(manifest)
    live_providers = _live_provider_ids(provider_payload)
    registered_bindings = _registered_identity_bindings(manifest)
    live_bindings = _live_identity_bindings(identity_binding_payload)
    registered_credentials = _registered_credential_profiles(manifest)
    live_credentials = _live_credential_profiles(credential_profile_payload)

    registered_containers = _registered_operational_containers(manifest)
    live_containers = _live_container_names(container_payload)
    live_containers -= {str(item).strip() for item in ignored_live_containers if str(item).strip()}

    return CompletenessResult(
        missing_capabilities=tuple(sorted(active_caps - registered_caps)),
        missing_providers=tuple(sorted(live_providers - registered_providers)),
        missing_identity_bindings=tuple(sorted(live_bindings - registered_bindings)),
        missing_credential_profiles=tuple(sorted(live_credentials - registered_credentials)),
        missing_components=tuple(sorted(live_containers - registered_containers)),
        stale_components=tuple(sorted(registered_containers - live_containers)),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail closed when live Jason production state is not fully represented in the System Registry."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--capabilities", type=Path, required=True)
    parser.add_argument("--providers", type=Path, required=True)
    parser.add_argument("--identity-bindings", type=Path, required=True)
    parser.add_argument("--credential-profiles", type=Path, required=True)
    parser.add_argument("--containers", type=Path, required=True)
    parser.add_argument(
        "--ignore-live-container",
        action="append",
        default=[],
        help="Explicitly exclude non-production/ephemeral containers such as buildkit builders.",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit(
        manifest=_load_json(args.manifest),
        capability_payload=_load_json(args.capabilities),
        provider_payload=_load_json(args.providers),
        identity_binding_payload=_load_json(args.identity_bindings),
        credential_profile_payload=_load_json(args.credential_profiles),
        container_payload=_load_json(args.containers),
        ignored_live_containers=args.ignore_live_container,
    )
    encoded = json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(args.output)
    else:
        print(encoded, end="")
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
