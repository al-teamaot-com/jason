from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from .provider_documentation_reader import (
    ProviderDocumentationCandidateFinding,
    ProviderDocumentationSourceRecord,
)


class SemanticEvidenceReviewStatus(str, Enum):
    INSUFFICIENT = "insufficient"
    AMBIGUOUS = "ambiguous"
    PROPOSAL_ELIGIBLE = "proposal_eligible"


@dataclass(frozen=True, slots=True)
class SemanticEvidenceReview:
    provider_id: str
    unsupported_fact: str
    documented_schema: str | None
    documented_field: str | None
    field_type: str | None
    field_description: str | None
    response_operations: tuple[str, ...]
    source_reference: str
    status: SemanticEvidenceReviewStatus
    semantic_mapping_approved: bool = False
    proposal_allowed: bool = False
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.semantic_mapping_approved:
            raise PermissionError(
                "semantic evidence review cannot approve semantic mappings"
            )

        if (
            self.status is SemanticEvidenceReviewStatus.PROPOSAL_ELIGIBLE
            and not self.proposal_allowed
        ):
            raise ValueError(
                "proposal-eligible review must explicitly allow proposal creation"
            )

        if (
            self.status is not SemanticEvidenceReviewStatus.PROPOSAL_ELIGIBLE
            and self.proposal_allowed
        ):
            raise ValueError(
                "only proposal-eligible evidence may allow proposal creation"
            )

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "unsupported_fact": self.unsupported_fact,
            "documented_schema": self.documented_schema,
            "documented_field": self.documented_field,
            "field_type": self.field_type,
            "field_description": self.field_description,
            "response_operations": self.response_operations,
            "source_reference": self.source_reference,
            "status": self.status.value,
            "semantic_mapping_approved": False,
            "proposal_allowed": self.proposal_allowed,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class GovernedOpenApiSemanticEvidenceReviewer:
    require_read_only_response_path: bool = True

    def review(
        self,
        *,
        finding: ProviderDocumentationCandidateFinding,
        source: ProviderDocumentationSourceRecord,
    ) -> SemanticEvidenceReview:
        if finding.semantic_proof:
            raise PermissionError(
                "semantic evidence review cannot consume pre-approved semantic proof"
            )

        if not finding.documented_schema or not finding.documented_field:
            return SemanticEvidenceReview(
                provider_id=finding.provider_id,
                unsupported_fact=finding.unsupported_fact,
                documented_schema=finding.documented_schema,
                documented_field=finding.documented_field,
                field_type=None,
                field_description=None,
                response_operations=(),
                source_reference=finding.source_reference,
                status=SemanticEvidenceReviewStatus.INSUFFICIENT,
                rationale=(
                    "Candidate does not identify both a concrete schema and field."
                ),
            )

        try:
            document = json.loads(source.content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "semantic evidence review requires valid OpenAPI JSON"
            ) from exc

        if not isinstance(document, Mapping):
            raise ValueError("OpenAPI document must be a JSON object")

        schema = (
            document.get("components", {})
            .get("schemas", {})
            .get(finding.documented_schema)
        )

        if not isinstance(schema, Mapping):
            return SemanticEvidenceReview(
                provider_id=finding.provider_id,
                unsupported_fact=finding.unsupported_fact,
                documented_schema=finding.documented_schema,
                documented_field=finding.documented_field,
                field_type=None,
                field_description=None,
                response_operations=(),
                source_reference=finding.source_reference,
                status=SemanticEvidenceReviewStatus.INSUFFICIENT,
                rationale="Documented schema was not found in the authoritative source.",
            )

        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            properties = {}

        raw_field = properties.get(finding.documented_field)
        if not isinstance(raw_field, Mapping):
            return SemanticEvidenceReview(
                provider_id=finding.provider_id,
                unsupported_fact=finding.unsupported_fact,
                documented_schema=finding.documented_schema,
                documented_field=finding.documented_field,
                field_type=None,
                field_description=None,
                response_operations=(),
                source_reference=finding.source_reference,
                status=SemanticEvidenceReviewStatus.INSUFFICIENT,
                rationale="Documented field was not found in the authoritative schema.",
            )

        field_type = str(raw_field.get("type", "")).strip() or None
        field_description = (
            str(raw_field.get("description", "")).strip() or None
        )

        operations = self._operations_returning_schema(
            document=document,
            schema_name=finding.documented_schema,
        )

        if self.require_read_only_response_path:
            read_only_operations = tuple(
                item for item in operations if item.startswith("GET ")
            )
        else:
            read_only_operations = operations

        if not field_description:
            return SemanticEvidenceReview(
                provider_id=finding.provider_id,
                unsupported_fact=finding.unsupported_fact,
                documented_schema=finding.documented_schema,
                documented_field=finding.documented_field,
                field_type=field_type,
                field_description=None,
                response_operations=read_only_operations,
                source_reference=finding.source_reference,
                status=SemanticEvidenceReviewStatus.AMBIGUOUS,
                rationale=(
                    "The field exists in the authoritative schema, but no field "
                    "description establishes its semantics."
                ),
            )

        if self.require_read_only_response_path and not read_only_operations:
            return SemanticEvidenceReview(
                provider_id=finding.provider_id,
                unsupported_fact=finding.unsupported_fact,
                documented_schema=finding.documented_schema,
                documented_field=finding.documented_field,
                field_type=field_type,
                field_description=field_description,
                response_operations=(),
                source_reference=finding.source_reference,
                status=SemanticEvidenceReviewStatus.AMBIGUOUS,
                rationale=(
                    "The field is documented, but no read-only operation was found "
                    "that returns its containing schema."
                ),
            )

        return SemanticEvidenceReview(
            provider_id=finding.provider_id,
            unsupported_fact=finding.unsupported_fact,
            documented_schema=finding.documented_schema,
            documented_field=finding.documented_field,
            field_type=field_type,
            field_description=field_description,
            response_operations=read_only_operations,
            source_reference=finding.source_reference,
            status=SemanticEvidenceReviewStatus.PROPOSAL_ELIGIBLE,
            proposal_allowed=True,
            rationale=(
                "Authoritative documentation defines the field and its description, "
                "and the containing schema is returned by at least one governed "
                "read-only documented operation. This permits a semantic mapping "
                "proposal for Technology Steward review but does not approve or "
                "activate that mapping."
            ),
        )

    def _operations_returning_schema(
        self,
        *,
        document: Mapping[str, Any],
        schema_name: str,
    ) -> tuple[str, ...]:
        paths = document.get("paths", {})
        if not isinstance(paths, Mapping):
            return ()

        needle = f"#/components/schemas/{schema_name}"
        found: set[str] = set()

        for path_name, raw_path in paths.items():
            if not isinstance(raw_path, Mapping):
                continue

            for method, operation in raw_path.items():
                method_name = str(method).casefold()
                if method_name not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                }:
                    continue

                if not isinstance(operation, Mapping):
                    continue

                responses = operation.get("responses", {})
                if self._contains_schema_reference(responses, needle):
                    found.add(
                        f"{method_name.upper()} {path_name}"
                    )

        return tuple(sorted(found))

    def _contains_schema_reference(
        self,
        value: Any,
        needle: str,
    ) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key) == "$ref" and str(child) == needle:
                    return True
                if self._contains_schema_reference(child, needle):
                    return True
            return False

        if isinstance(value, (list, tuple)):
            return any(
                self._contains_schema_reference(child, needle)
                for child in value
            )

        return False
