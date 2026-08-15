from __future__ import annotations

from dataclasses import dataclass

from kernel.capabilities import CapabilityRegistryService

from .semantic_fact_resolver import SemanticFactResolver
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
    """Require explicit governed coverage for semantic facts Jason recognizes.

    Semantic recognition answers only *what the human means*. It must not silently
    create retrieval authority. Before delegating to normal resource planning, this
    boundary checks that every explicitly recognized registry fact is declared by an
    active provider-neutral read capability or an approved semantic mapping.
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
            canonical = resolution.canonical_fact
            if not self._has_coverage(canonical):
                uncovered.append(canonical)

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

    def _has_coverage(self, canonical_fact: str) -> bool:
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
