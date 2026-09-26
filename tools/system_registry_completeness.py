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
    missing_components: tuple[str, ...]
    stale_components: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (self.missing_capabilities or self.missing_components or self.stale_components)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "pass" if self.passed else "fail",
            "missing_capabilities": list(self.missing_capabilities),
            "missing_components": list(self.missing_components),
            "stale_components": list(self.stale_components),
            "summary": {
                "missing_capability_count": len(self.missing_capabilities),
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
    container_payload: object,
    ignored_live_containers: Iterable[str] = (),
) -> CompletenessResult:
    registered_caps = _registered_capability_names(manifest)
    active_caps = _active_capability_names(capability_payload)

    registered_containers = _registered_operational_containers(manifest)
    live_containers = _live_container_names(container_payload)
    live_containers -= {str(item).strip() for item in ignored_live_containers if str(item).strip()}

    return CompletenessResult(
        missing_capabilities=tuple(sorted(active_caps - registered_caps)),
        missing_components=tuple(sorted(live_containers - registered_containers)),
        stale_components=tuple(sorted(registered_containers - live_containers)),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail closed when live Jason production state is not fully represented in the System Registry."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--capabilities", type=Path, required=True)
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
