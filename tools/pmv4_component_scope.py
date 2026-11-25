#!/usr/bin/env python3
"""PMv4 source-scope protection based on Jason's EXISTING System Registry.

This is a preproduction admission guard for component-scoped releases, not a
new component registry, authority engine, deployment service or production
policy. Proposed entities do not imply active service or approved mutation.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath
from typing import Iterable

from kernel.system_registry.manifest import registry_from_manifest
from kernel.system_registry.repository import RegistryEntityNotFoundError

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "implementation/kernel/system_registry/production-registry.json"
PROTECTED = frozenset((
    "component.ticket-processing-core",
    "component.runbook-management",
))
# Source files that span multiple independently governed components must not
# be smuggled into a single-component release, even if they have no exclusive
# owner in the registry's source_globs.
SHARED = frozenset((
    "implementation/runtime_service/src/jason_runtime/main.py",
    "implementation/runtime_service/src/jason_runtime/composition.py",
    "implementation/runtime_service/src/jason_runtime/maintenance_process.py",
    "implementation/mcp_service/src/jason_mcp/server.py",
    "implementation/kernel/system_registry/production-registry.json",
    "config/release-manager-policy.json",
))


class ProtectedCoreScopeDenied(PermissionError):
    pass


def _registry_patterns(registry_path: Path) -> dict[str, tuple[str, ...]]:
    registry = registry_from_manifest(registry_path)
    patterns: dict[str, tuple[str, ...]] = {}
    for registry_id in sorted(PROTECTED):
        try:
            entry = registry.get(registry_id)
        except RegistryEntityNotFoundError as exc:
            raise ProtectedCoreScopeDenied("PMV4_PROTECTED_COMPONENT_MISSING") from exc
        settings = entry.declared_state
        if (
            entry.entity_type.value != "component"
            or settings.get("protected_core") != "true"
            or settings.get("component_lifecycle") != "independent"
            or settings.get("deployment_status") not in ("not_deployed", "deployed")
            or (entry.lifecycle_status.value == "proposed"
                and settings.get("deployment_status") != "not_deployed")
            or (entry.lifecycle_status.value == "active"
                and settings.get("deployment_status") != "deployed")
            or any("pmv3" in dep.lower() for dep in entry.dependencies)
        ):
            raise ProtectedCoreScopeDenied("PMV4_PROTECTED_COMPONENT_NOT_PREPROD")
        raw = settings.get("source_globs")
        if not isinstance(raw, str) or not raw.strip():
            raise ProtectedCoreScopeDenied("PMV4_PROTECTED_SOURCE_SCOPE_MISSING")
        items = tuple(pattern.strip() for pattern in raw.split(";"))
        if any(
            not item or item.startswith("/") or ".." in PurePosixPath(item).parts
            or "\\" in item or "**" in item or item == "*"
            for item in items
        ):
            raise ProtectedCoreScopeDenied("PMV4_PROTECTED_SOURCE_PATTERN_UNTRUSTED")
        patterns[registry_id] = items
    return patterns


def classify_source_paths(
    paths: Iterable[str], *, registry_path: Path = REGISTRY,
) -> dict[str, object]:
    patterns = _registry_patterns(registry_path)
    matches: dict[str, list[str]] = {name: [] for name in patterns}
    shared: list[str] = []
    normalized: set[str] = set()
    for path in paths:
        if not isinstance(path, str) or not path:
            raise ProtectedCoreScopeDenied("PMV4_COMPONENT_SOURCE_PATH_INVALID")
        pp = PurePosixPath(path)
        if path.startswith("/") or "\\" in path or ".." in pp.parts or str(pp) != path:
            raise ProtectedCoreScopeDenied("PMV4_COMPONENT_SOURCE_PATH_INVALID")
        normalized.add(path)
        if path in SHARED:
            shared.append(path)
        for registry_id, globs in patterns.items():
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in globs):
                matches[registry_id].append(path)
    return {
        "matched": {key: sorted(value) for key, value in matches.items() if value},
        "shared": sorted(set(shared)),
        "path_count": len(normalized),
    }


def assert_component_release_scope(
    paths: Iterable[str], *, component: str,
    registry_path: Path = REGISTRY,
) -> dict[str, object]:
    if component not in (*sorted(PROTECTED), "pmv4-shadow"):
        raise ProtectedCoreScopeDenied("PMV4_COMPONENT_RELEASE_TARGET_INVALID")
    classified = classify_source_paths(paths, registry_path=registry_path)
    affected = set(classified["matched"])
    if classified["shared"]:
        raise ProtectedCoreScopeDenied("PMV4_SHARED_CORE_REQUIRES_CROSS_COMPONENT_RELEASE")
    if component == "pmv4-shadow" and affected:
        raise ProtectedCoreScopeDenied("PMV4_SHADOW_CANNOT_CHANGE_PROTECTED_CORE")
    if affected - {component}:
        raise ProtectedCoreScopeDenied("PMV4_CROSS_COMPONENT_CHANGE_DENIED")
    if component in PROTECTED and component not in affected:
        raise ProtectedCoreScopeDenied("PMV4_COMPONENT_SCOPE_EMPTY_OR_UNVERIFIED")
    return classified
