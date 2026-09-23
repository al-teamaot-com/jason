from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_intent_planning_loop import PlanningContextRequest


@dataclass(frozen=True, slots=True)
class ProviderNeutralIntentContextBootstrapper:
    """Derive bounded governed context prerequisites from provider-neutral intent.

    The bootstrapper does not select providers, connectors, agents, tools, or execution
    routes. It only ensures the reasoner begins with semantic meaning and registered
    capability context instead of spending reasoning turns rediscovering those basics.
    """

    def requests_for(self, *, intent: Mapping[str, Any]) -> tuple[PlanningContextRequest, ...]:
        requested_facts = intent.get("requested_facts", ())
        if isinstance(requested_facts, str):
            facts = (requested_facts.strip(),) if requested_facts.strip() else ()
        elif isinstance(requested_facts, (list, tuple, set, frozenset)):
            facts = tuple(str(item).strip() for item in requested_facts if str(item).strip())
        else:
            facts = ()

        resource_type = str(intent.get("resource_type", "")).strip()
        human_text = str(intent.get("human_text", "")).strip()

        semantic_query = " ".join(facts[:3]).strip() or human_text[:160].strip()
        capability_query = resource_type or " ".join(facts[:2]).strip() or human_text[:120].strip()

        requests: list[PlanningContextRequest] = []
        if semantic_query:
            requests.append(
                PlanningContextRequest(
                    view="semantic_knowledge",
                    query={"query": semantic_query},
                    purpose="establish governed meaning for the requested fact or relationship",
                )
            )
        if capability_query:
            requests.append(
                PlanningContextRequest(
                    view="capability_registry",
                    query={"query": capability_query},
                    purpose="establish governed provider-neutral capabilities relevant to the intent",
                )
            )
        return tuple(requests)
