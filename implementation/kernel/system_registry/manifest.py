from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from kernel.system_registry.contracts import (
    CredentialReference,
    EntityLifecycle,
    EntityType,
    RegistryEntity,
)
from kernel.system_registry.repository import InMemorySystemRegistry


SCHEMA_PATH = Path(__file__).with_name("system-registry.schema.json")


def load_manifest_document(path: Path) -> Mapping[str, Any]:
    """Load and schema-validate a System Registry manifest."""

    document = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        detail = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"System Registry manifest is invalid: {detail}")
    return document


def registry_from_manifest(path: Path) -> InMemorySystemRegistry:
    """Create an in-memory registry from a governed machine-readable manifest.

    Registration order in the file is not authoritative. Dependencies are resolved
    deterministically so generated manifests can be organized for humans without
    weakening topology validation.
    """

    document = load_manifest_document(path)
    entities = {
        str(raw["registry_id"]): _entity_from_mapping(raw)
        for raw in document["entities"]
    }
    if len(entities) != len(document["entities"]):
        raise ValueError("System Registry manifest contains duplicate registry IDs.")

    registry = InMemorySystemRegistry()
    pending = dict(entities)
    while pending:
        progressed = False
        registered = {entity.registry_id for entity in registry.list_all()}
        for registry_id, entity in list(pending.items()):
            if not entity.dependencies.issubset(registered):
                continue
            registry.register(entity)
            del pending[registry_id]
            progressed = True
        if progressed:
            continue

        unresolved = ", ".join(
            f"{registry_id} -> {','.join(sorted(entity.dependencies))}"
            for registry_id, entity in sorted(pending.items())
        )
        raise ValueError(
            "System Registry manifest contains missing or cyclic dependencies: "
            + unresolved
        )

    return registry


def _entity_from_mapping(raw: Mapping[str, Any]) -> RegistryEntity:
    credentials = tuple(
        CredentialReference(
            provider=str(item["provider"]),
            reference=str(item["reference"]),
        )
        for item in raw.get("credential_references", [])
    )
    return RegistryEntity(
        registry_id=str(raw["registry_id"]),
        entity_type=EntityType(str(raw["entity_type"])),
        display_name=str(raw["display_name"]),
        environment=str(raw["environment"]),
        lifecycle_status=EntityLifecycle(str(raw["lifecycle_status"])),
        declared_state={str(key): str(value) for key, value in raw["declared_state"].items()},
        dependencies=frozenset(str(item) for item in raw["dependencies"]),
        verification_methods=tuple(str(item) for item in raw["verification_methods"]),
        steward=str(raw["steward"]),
        authority_references=tuple(str(item) for item in raw.get("authority_references", [])),
        credential_references=credentials,
        evidence_references=tuple(str(item) for item in raw.get("evidence_references", [])),
        source_version=(
            None if raw.get("source_version") is None else str(raw["source_version"])
        ),
        created_at=_parse_datetime(raw.get("created_at")),
        created_by=None if raw.get("created_by") is None else str(raw["created_by"]),
        metadata={str(key): str(value) for key, value in raw.get("metadata", {}).items()},
    )


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if rendered.endswith("Z"):
        rendered = rendered[:-1] + "+00:00"
    return datetime.fromisoformat(rendered)
