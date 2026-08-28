from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .provider_documentation_reader import (
    ProviderDocumentationCandidateFinding,
    ProviderDocumentationSourceRecord,
)


@dataclass(frozen=True, slots=True)
class CorroboratingEvidence:
    provider_id: str
    unsupported_fact: str
    documented_schema: str
    documented_field: str
    schema_description: str | None
    field_description: str | None
    field_type: str | None
    field_example: object | None
    field_default: object | None
    field_enum: tuple[object, ...]
    sibling_fields: tuple[str, ...]
    read_only_operations: tuple[str, ...]
    source_reference: str
    semantic_proof: bool = False

    def __post_init__(self) -> None:
        if self.semantic_proof:
            raise PermissionError(
                "corroborating documentation evidence cannot establish semantic proof"
            )

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "unsupported_fact": self.unsupported_fact,
            "documented_schema": self.documented_schema,
            "documented_field": self.documented_field,
            "schema_description": self.schema_description,
            "field_description": self.field_description,
            "field_type": self.field_type,
            "field_example": self.field_example,
            "field_default": self.field_default,
            "field_enum": self.field_enum,
            "sibling_fields": self.sibling_fields,
            "read_only_operations": self.read_only_operations,
            "source_reference": self.source_reference,
            "semantic_proof": False,
        }


@dataclass(frozen=True, slots=True)
class GovernedOpenApiCorroboratingEvidenceReviewer:
    max_sibling_fields: int = 25

    def __post_init__(self) -> None:
        if self.max_sibling_fields < 1:
            raise ValueError("max_sibling_fields must be positive")

    def review(
        self,
        *,
        finding: ProviderDocumentationCandidateFinding,
        source: ProviderDocumentationSourceRecord,
    ) -> CorroboratingEvidence:
        if finding.semantic_proof:
            raise PermissionError(
                "corroborating evidence review cannot consume semantic proof"
            )

        if not finding.documented_schema or not finding.documented_field:
            raise ValueError(
                "corroborating evidence review requires a concrete schema and field"
            )

        try:
            document = json.loads(source.content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "corroborating evidence review requires valid OpenAPI JSON"
            ) from exc

        if not isinstance(document, Mapping):
            raise ValueError("OpenAPI document must be a JSON object")

        schemas = document.get("components", {}).get("schemas", {})
        if not isinstance(schemas, Mapping):
            raise ValueError("OpenAPI document has no schema registry")

        schema = schemas.get(finding.documented_schema)
        if not isinstance(schema, Mapping):
            raise ValueError("candidate schema is absent from authoritative source")

        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ValueError("candidate schema has no property registry")

        field = properties.get(finding.documented_field)
        if not isinstance(field, Mapping):
            raise ValueError("candidate field is absent from authoritative schema")

        schema_description = (
            str(schema.get("description", "")).strip() or None
        )
        field_description = (
            str(field.get("description", "")).strip() or None
        )
        field_type = str(field.get("type", "")).strip() or None

        raw_enum = field.get("enum", ())
        if isinstance(raw_enum, list):
            field_enum = tuple(raw_enum)
        else:
            field_enum = ()

        sibling_fields = tuple(
            sorted(
                str(name)
                for name in properties.keys()
                if str(name) != finding.documented_field
            )[: self.max_sibling_fields]
        )

        read_only_operations = self._read_only_operations_returning_schema(
            document=document,
            schema_name=finding.documented_schema,
        )

        return CorroboratingEvidence(
            provider_id=finding.provider_id,
            unsupported_fact=finding.unsupported_fact,
            documented_schema=finding.documented_schema,
            documented_field=finding.documented_field,
            schema_description=schema_description,
            field_description=field_description,
            field_type=field_type,
            field_example=field.get("example"),
            field_default=field.get("default"),
            field_enum=field_enum,
            sibling_fields=sibling_fields,
            read_only_operations=read_only_operations,
            source_reference=finding.source_reference,
            semantic_proof=False,
        )

    def _read_only_operations_returning_schema(
        self,
        *,
        document: Mapping[str, Any],
        schema_name: str,
    ) -> tuple[str, ...]:
        paths = document.get("paths", {})
        if not isinstance(paths, Mapping):
            return ()

        needle = f"#/components/schemas/{schema_name}"
        operations: set[str] = set()

        for path_name, raw_path in paths.items():
            if not isinstance(raw_path, Mapping):
                continue

            operation = raw_path.get("get")
            if not isinstance(operation, Mapping):
                continue

            responses = operation.get("responses", {})
            if self._contains_ref(responses, needle):
                operations.add(f"GET {path_name}")

        return tuple(sorted(operations))

    def _contains_ref(
        self,
        value: Any,
        needle: str,
    ) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key) == "$ref" and str(child) == needle:
                    return True
                if self._contains_ref(child, needle):
                    return True
            return False

        if isinstance(value, (list, tuple)):
            return any(self._contains_ref(child, needle) for child in value)

        return False
