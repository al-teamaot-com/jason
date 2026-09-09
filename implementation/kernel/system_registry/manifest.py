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
    VerificationOutcome,
    VerificationRecord,
)
from kernel.system_registry.repository import InMemorySystemRegistry


SCHEMA_PATH = Path(__file__).with_name("system-registry.schema.json")
LIFECYCLE_EVENTS_SCHEMA_PATH = Path(__file__).with_name(
    "system-registry-lifecycle-events.schema.json"
)


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


def load_lifecycle_events_document(path: Path) -> Mapping[str, Any]:
    """Load and schema-validate append-only governed lifecycle events."""

    document = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(LIFECYCLE_EVENTS_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        detail = "; ".join(error.message for error in errors[:5])
        raise ValueError(f"System Registry lifecycle events are invalid: {detail}")
    return document


def registry_from_manifest(
    path: Path,
    *,
    lifecycle_events_path: Path | None = None,
) -> InMemorySystemRegistry:
    """Create an in-memory registry from governed machine-readable state.

    The manifest describes the baseline declared registry. Optional lifecycle events
    are applied afterward in deterministic time/event order. Keeping lifecycle
    transitions as explicit events preserves why, when, and under whose authority
    effective operational state advanced without rewriting historical evidence.

    Registration order in the manifest is not authoritative. Dependencies are
    resolved deterministically so generated manifests can be organized for humans
    without weakening topology validation.
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

    if lifecycle_events_path is not None:
        _apply_lifecycle_events(registry, lifecycle_events_path)

    return registry


def _apply_lifecycle_events(
    registry: InMemorySystemRegistry,
    path: Path,
) -> None:
    document = load_lifecycle_events_document(path)
    raw_events = list(document["events"])
    event_ids = [str(event["event_id"]) for event in raw_events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("System Registry lifecycle events contain duplicate event IDs.")

    events = sorted(
        raw_events,
        key=lambda event: (
            _parse_required_datetime(event["effective_at"]),
            str(event["event_id"]),
        ),
    )

    for event in events:
        event_id = str(event["event_id"])
        registry_id = str(event["registry_id"])
        current = registry.get(registry_id)
        expected_from = EntityLifecycle(str(event["from_lifecycle"]))
        target = EntityLifecycle(str(event["to_lifecycle"]))
        if current.lifecycle_status is not expected_from:
            raise ValueError(
                f"Lifecycle event {event_id} expected {registry_id} to be "
                f"{expected_from.value}, found {current.lifecycle_status.value}."
            )

        if target in {EntityLifecycle.VERIFIED, EntityLifecycle.ACTIVE}:
            method = str(event["verification_method"])
            if str(event["verification_outcome"]) != VerificationOutcome.VERIFIED.value:
                raise ValueError(
                    f"Lifecycle event {event_id} cannot promote without verified evidence."
                )
            registry.record_verification(
                VerificationRecord(
                    registry_id=registry_id,
                    method=method,
                    outcome=VerificationOutcome.VERIFIED,
                    verified_at=_parse_required_datetime(event["effective_at"]),
                    observation_source="governed-system-registry-lifecycle-event",
                    evidence_references=tuple(
                        str(item) for item in event["evidence_references"]
                    ),
                    detail=(
                        f"Lifecycle event {event_id}; principal="
                        f"{str(event['principal_id'])}; reason={str(event['reason'])}"
                    ),
                )
            )

        registry.transition_lifecycle(
            registry_id=registry_id,
            lifecycle_status=target,
        )


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


def _parse_required_datetime(value: object) -> datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError("Lifecycle event effective_at must be a date-time.")
    return parsed


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if rendered.endswith("Z"):
        rendered = rendered[:-1] + "+00:00"
    return datetime.fromisoformat(rendered)
