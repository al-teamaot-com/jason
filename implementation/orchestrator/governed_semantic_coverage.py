from __future__ import annotations

from dataclasses import dataclass

from kernel.capabilities import CapabilityRegistryService

from .semantic_capability_coverage import semantic_resolution_matches_resource_contract
from .semantic_fact_resolver import SemanticFactResolution, SemanticFactResolver
from .semantic_mapping_registry import SemanticMappingRegistry
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationGuidanceRequiredError,
    ConversationIntent,
    ConversationIntentPlan,
    ConversationIntentResolver,
)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").split())


@dataclass(frozen=True, slots=True)
class GovernedSemanticCoverageIntentResolver:
    """Require governed coverage for semantic facts Jason recognizes.

    Semantic recognition answers only *what the human means*. It must not silently
    create retrieval authority. Before delegating to normal resource planning, this
    boundary checks that every explicitly recognized registry fact is covered by
    provider-neutral read capability structure, legacy declared canonical coverage,
    or an approved semantic mapping.

    Structural coverage is intentionally resource-based rather than phrase-based:
    active semantic concepts are compared with governed capability ``resource_types``
    by semantic namespace/evidence context. This allows Jason to evolve endpoint facts
    without adding one static question-to-fact mapping for every new observation.
    """

    delegate: ConversationIntentResolver
    capabilities: CapabilityRegistryService
    fact_resolver: SemanticFactResolver
    semantic_mapping_registry: SemanticMappingRegistry | None = None

    def resolve(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ConversationIntent | ConversationIntentPlan | None:
        explicit = self.fact_resolver.match_explicit_facts(text)
        uncovered: list[str] = []
        for resolution in explicit:
            if not self._has_coverage(resolution):
                uncovered.append(resolution.canonical_fact)

        if uncovered:
            unique = tuple(dict.fromkeys(uncovered))
            if len(unique) == 1:
                subject = unique[0]
            else:
                subject = ", ".join(unique)
            raise ConversationGuidanceRequiredError(
                reason_code="governed_fact_not_available",
                guidance_text=(
                    f"I recognized that as a request for {subject}, but Jason does not "
                    "currently have a governed read capability that declares authority "
                    "to retrieve that fact. No provider request was made."
                ),
                requested_facts=unique,
            )

        return self.delegate.resolve(text=text, principal=principal)

    def _has_coverage(self, resolution: SemanticFactResolution) -> bool:
        canonical_fact = resolution.canonical_fact
        wanted = _normalized(canonical_fact)

        if self.semantic_mapping_registry is not None:
            if self.semantic_mapping_registry.find_active(canonical_fact=canonical_fact):
                return True

        for capability in self.capabilities.list_all():
            metadata = capability.metadata
            if metadata.get("provider_neutral", "false").casefold() != "true":
                continue
            if metadata.get("read_only", "false").casefold() != "true":
                continue

            if semantic_resolution_matches_resource_contract(
                resolution=resolution,
                metadata=metadata,
            ):
                return True

            # Transitional compatibility for governed facts not yet represented by
            # structural Semantic Knowledge Registry concepts. This is deliberately
            # not expanded for new facts; the target architecture is structural.
            declared = {
                _normalized(item)
                for item in metadata.get("canonical_facts", "").split(",")
                if item.strip()
            }
            collection = str(metadata.get("collection_fact", "")).strip()
            if collection:
                declared.add(_normalized(collection))
            if wanted in declared:
                return True
        return False
