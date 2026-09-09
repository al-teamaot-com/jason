from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


class PlanningContextViewUnavailableError(LookupError):
    """A requested governed planning view is unavailable."""


@dataclass(frozen=True, slots=True)
class PlanningContextRequest:
    view_name: str
    query: str = ""
    limit: int = 32

    def __post_init__(self) -> None:
        if not self.view_name.strip():
            raise ValueError("planning context view_name is required")
        if self.limit < 1 or self.limit > 128:
            raise ValueError("planning context limit is invalid")


@dataclass(frozen=True, slots=True)
class PlanningContextView:
    view_name: str
    items: tuple[Mapping[str, Any], ...]
    authoritative: bool = True
    truncated: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


class PlanningContextProvider(Protocol):
    def read(self, request: PlanningContextRequest) -> PlanningContextView: ...


@dataclass(frozen=True, slots=True)
class GovernedPlanningContextCatalog:
    """Expose bounded, provider-neutral planning context to a reasoner.

    The catalog never invokes providers, tools, connectors, agents, or credentials.
    It only returns deterministic views over already-governed Jason registries/state.
    """

    providers: Mapping[str, PlanningContextProvider]
    allowed_views: tuple[str, ...] = (
        "semantic_knowledge",
        "capabilities",
        "system_state",
        "evidence_catalog",
        "derivations",
    )

    def read(self, request: PlanningContextRequest) -> PlanningContextView:
        view_name = request.view_name.strip()
        if view_name not in self.allowed_views:
            raise PermissionError("planning context view is not allowed")
        provider = self.providers.get(view_name)
        if provider is None:
            raise PlanningContextViewUnavailableError(
                f"planning context view unavailable: {view_name}"
            )
        view = provider.read(request)
        if view.view_name != view_name:
            raise RuntimeError("planning context provider changed requested view name")
        if len(view.items) > request.limit:
            raise RuntimeError("planning context provider exceeded requested limit")
        return view


@dataclass(frozen=True, slots=True)
class StaticPlanningContextProvider:
    """Deterministic test/bootstrap view over already-governed records."""

    view_name: str
    records: Sequence[Mapping[str, Any]]
    searchable_fields: tuple[str, ...] = ()

    def read(self, request: PlanningContextRequest) -> PlanningContextView:
        query = request.query.strip().casefold()
        matched = []
        for record in self.records:
            if query:
                values = []
                fields = self.searchable_fields or tuple(record.keys())
                for field in fields:
                    value = record.get(field)
                    if value is not None:
                        values.append(str(value).casefold())
                if not any(query in value for value in values):
                    continue
            matched.append(dict(record))
            if len(matched) >= request.limit:
                break
        return PlanningContextView(
            view_name=self.view_name,
            items=tuple(matched),
            authoritative=True,
            truncated=len(matched) >= request.limit and len(self.records) > len(matched),
        )
