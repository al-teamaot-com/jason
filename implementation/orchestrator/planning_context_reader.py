from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .planning_context_views import (
    GovernedPlanningContextCatalog,
    PlanningContextRequest as CatalogPlanningContextRequest,
)
from .semantic_intent_planning_loop import PlanningContextRequest


_VIEW_NAME_MAP = {
    "semantic_knowledge": "semantic_knowledge",
    "capability_registry": "capabilities",
    "system_registry": "system_state",
    "evidence_catalog": "evidence_catalog",
    "derivation_registry": "derivations",
}


@dataclass(frozen=True, slots=True)
class GovernedPlanningContextReaderAdapter:
    """Adapt the governed context catalog to the planning-loop read contract.

    This adapter has no provider, connector, tool, agent, credential, or execution
    authority. It only translates between two provider-neutral governed contracts.
    """

    catalog: GovernedPlanningContextCatalog
    default_limit: int = 32

    def __post_init__(self) -> None:
        if self.default_limit < 1 or self.default_limit > 128:
            raise ValueError("default planning context limit is invalid")

    def read(
        self,
        *,
        request: PlanningContextRequest,
        intent: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del intent  # authorization/intent remain owned by the orchestrator contract.

        catalog_view_name = _VIEW_NAME_MAP.get(request.view)
        if catalog_view_name is None:
            raise PermissionError(f"planning context view is not governed: {request.view}")

        query = self._query_text(request.query)
        view = self.catalog.read(
            CatalogPlanningContextRequest(
                view_name=catalog_view_name,
                query=query,
                limit=self.default_limit,
            )
        )

        result: dict[str, Any] = {
            "view_name": request.view,
            "items": tuple(dict(item) for item in view.items),
            "authoritative": bool(view.authoritative),
            "truncated": bool(view.truncated),
        }
        if request.view == "capability_registry":
            result["capability_names"] = tuple(
                str(item.get("capability_name", "")).strip()
                for item in view.items
                if str(item.get("capability_name", "")).strip()
            )
        return result

    @staticmethod
    def _query_text(query: Mapping[str, Any]) -> str:
        preferred = (
            "concept",
            "concept_id",
            "fact",
            "resource_type",
            "capability_name",
            "relationship_type",
            "query",
        )
        for key in preferred:
            value = query.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        scalar_values = [
            str(value).strip()
            for value in query.values()
            if isinstance(value, (str, int, float)) and str(value).strip()
        ]
        return " ".join(scalar_values[:4])
