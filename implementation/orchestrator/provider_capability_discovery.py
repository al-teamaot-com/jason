from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from kernel.execution_providers import ExecutionProvider
from .semantic_capability_gap import SemanticCapabilityGapAssessment


@dataclass(frozen=True, slots=True)
class ProviderCapabilityDiscoveryCandidate:
    provider_id: str
    display_name: str
    registered_capabilities: tuple[str, ...]
    vendor_change_sources: tuple[str, ...]
    technology_steward: str
    resource_authority: str | None = None
    connector_id: str | None = None

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "registered_capabilities": self.registered_capabilities,
            "vendor_change_sources": self.vendor_change_sources,
            "technology_steward": self.technology_steward,
            "resource_authority": self.resource_authority,
            "connector_id": self.connector_id,
        }


@dataclass(frozen=True, slots=True)
class ProviderCapabilityDiscoveryAssessment:
    unsupported_facts: tuple[str, ...]
    candidates: tuple[ProviderCapabilityDiscoveryCandidate, ...]
    review_only: bool = True
    governance_owner: str = "technology-steward"

    def as_context(self) -> Mapping[str, object]:
        return {
            "unsupported_facts": self.unsupported_facts,
            "review_only": self.review_only,
            "governance_owner": self.governance_owner,
            "candidates": tuple(item.as_context() for item in self.candidates),
        }


@dataclass(frozen=True, slots=True)
class GovernedProviderCapabilityDiscovery:
    """Identify registered providers whose authoritative documentation should be reviewed.

    This layer is intentionally review-only. It does not call providers, inspect credentials,
    infer semantic mappings, mutate capability metadata, or select an execution provider.
    It only narrows a proven capability gap to already-registered providers and the authoritative
    vendor documentation sources recorded in provider stewardship metadata.
    """

    def discover(
        self,
        *,
        gap: SemanticCapabilityGapAssessment,
        providers: Sequence[ExecutionProvider],
    ) -> ProviderCapabilityDiscoveryAssessment:
        candidates: list[ProviderCapabilityDiscoveryCandidate] = []
        for provider in providers:
            sources = tuple(
                str(item).strip()
                for item in provider.stewardship.vendor_change_sources
                if str(item).strip()
            )
            if not sources:
                continue
            metadata = dict(provider.metadata)
            candidates.append(
                ProviderCapabilityDiscoveryCandidate(
                    provider_id=provider.provider_id,
                    display_name=provider.display_name,
                    registered_capabilities=tuple(sorted(provider.capabilities)),
                    vendor_change_sources=sources,
                    technology_steward=provider.stewardship.technology_steward,
                    resource_authority=(
                        str(metadata.get("resource_authority", "")).strip() or None
                    ),
                    connector_id=(str(metadata.get("connector_id", "")).strip() or None),
                )
            )

        candidates.sort(key=lambda item: (item.provider_id.casefold(), item.display_name.casefold()))
        return ProviderCapabilityDiscoveryAssessment(
            unsupported_facts=tuple(gap.unsupported_facts),
            candidates=tuple(candidates),
        )
