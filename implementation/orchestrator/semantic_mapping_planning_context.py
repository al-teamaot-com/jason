from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .planning_context_views import (
    PlanningContextRequest,
    PlanningContextView,
)
from .semantic_mapping_registry import SemanticMappingRegistry


@dataclass(frozen=True, slots=True)
class SemanticMappingPlanningContextProvider:
    registry: SemanticMappingRegistry
    view_name: str

    def __post_init__(self) -> None:
        if self.view_name not in {
            "semantic_knowledge",
            "derivations",
        }:
            raise ValueError(
                "semantic mapping planning provider supports only semantic or derivation views"
            )

    def read(
        self,
        request: PlanningContextRequest,
    ) -> PlanningContextView:
        query = request.query.strip()

        items = self.registry.as_context(
            query=query or None,
        )

        if self.view_name == "semantic_knowledge":
            records = tuple(
                {
                    "record_type": "approved_semantic_mapping",
                    "mapping_id": item["mapping_id"],
                    "mapping_version": item["version"],
                    "canonical_fact": item["canonical_fact"],
                    "provider_id": item["provider_id"],
                    "provider_schema": item["provider_schema"],
                    "provider_field": item["provider_field"],
                    "resource_authority": item["resource_authority"],
                    "capability_names": item["capability_names"],
                    "approval_status": item["approval_status"],
                    "active": item["active"],
                    "openapi_source_reference": item[
                        "openapi_source_reference"
                    ],
                    "semantic_source_reference": item[
                        "semantic_source_reference"
                    ],
                }
                for item in items[: request.limit]
            )
        else:
            records = tuple(
                {
                    "record_type": "approved_provider_fact_derivation",
                    "relationship_id": item["mapping_id"],
                    "canonical_fact": item["canonical_fact"],
                    "provider_id": item["provider_id"],
                    "provider_schema": item["provider_schema"],
                    "provider_field": item["provider_field"],
                    "resource_authority": item["resource_authority"],
                    "capability_names": item["capability_names"],
                    "approved": True,
                    "active": item["active"],
                    "evidence_references": (
                        item["openapi_source_reference"],
                        item["semantic_source_reference"],
                    ),
                }
                for item in items[: request.limit]
            )

        return PlanningContextView(
            view_name=self.view_name,
            items=records,
            authoritative=True,
            truncated=len(items) > request.limit,
            metadata={
                "source": "approved_semantic_mapping_registry",
            },
        )
