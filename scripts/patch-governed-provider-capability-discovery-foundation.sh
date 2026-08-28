#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START GOVERNED PROVIDER CAPABILITY DISCOVERY FOUNDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: ADD REVIEW-ONLY PROVIDER DISCOVERY CONTRACT =========="
cat > implementation/orchestrator/provider_capability_discovery.py <<'PY'
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
PY

echo "WROTE: implementation/orchestrator/provider_capability_discovery.py"

echo "========== SECTION 3: ADD PROVIDER-NEUTRAL REGRESSION COVERAGE =========="
cat > implementation/orchestrator/tests/test_provider_capability_discovery.py <<'PY'
from datetime import datetime, timezone

from kernel.execution_providers import (
    ExecutionProvider,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery
from orchestrator.semantic_capability_gap import SemanticCapabilityGapAssessment


def provider(*, provider_id: str, sources=()) -> ExecutionProvider:
    now = datetime.now(timezone.utc)
    return ExecutionProvider(
        provider_id=provider_id,
        display_name=provider_id.upper(),
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({"endpoint.device.search", "endpoint.device.read"}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="test",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="test provider",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("retire when replaced",),
            vendor_change_sources=tuple(sources),
        ),
        created_at=now,
        metadata={"connector_id": provider_id, "resource_authority": "managed_endpoint"},
    )


def test_gap_discovers_only_registered_providers_with_authoritative_sources():
    gap = SemanticCapabilityGapAssessment(
        unsupported_facts=("special fact",),
        inspected_context_views=("capability_registry", "evidence_catalog", "derivation_registry"),
    )
    result = GovernedProviderCapabilityDiscovery().discover(
        gap=gap,
        providers=(
            provider(provider_id="provider_b", sources=("Vendor B API docs",)),
            provider(provider_id="provider_a", sources=("Vendor A API docs",)),
            provider(provider_id="provider_without_docs"),
        ),
    )

    assert result.review_only is True
    assert result.unsupported_facts == ("special fact",)
    assert tuple(item.provider_id for item in result.candidates) == ("provider_a", "provider_b")
    assert result.candidates[0].vendor_change_sources == ("Vendor A API docs",)
    assert result.candidates[0].connector_id == "provider_a"
    assert result.candidates[0].resource_authority == "managed_endpoint"


def test_discovery_does_not_claim_provider_support_for_gap():
    gap = SemanticCapabilityGapAssessment(
        unsupported_facts=("unknown fact",),
        inspected_context_views=("capability_registry", "evidence_catalog", "derivation_registry"),
    )
    result = GovernedProviderCapabilityDiscovery().discover(
        gap=gap,
        providers=(provider(provider_id="provider_a", sources=("Vendor A API docs",)),),
    )
    context = result.as_context()

    assert context["review_only"] is True
    assert context["unsupported_facts"] == ("unknown fact",)
    assert "supported_facts" not in context
    assert "semantic_mapping" not in context
    assert "selected_provider" not in context
PY

echo "WROTE: implementation/orchestrator/tests/test_provider_capability_discovery.py"

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_provider_capability_discovery.py \
  implementation/orchestrator/tests/test_semantic_capability_gap.py \
  implementation/orchestrator/tests/test_semantic_fulfillment_feasibility.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Registered-provider capability discovery foundation added and validated in review-only mode."
echo "Discovery exposes only governed provider metadata and authoritative vendor documentation sources."
echo "It does not call providers, inspect credentials, infer semantic mappings, select providers, or mutate registries."
echo "NO RUNTIME WIRING PERFORMED."
echo "NO PROVIDER READ OR MUTATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED PROVIDER CAPABILITY DISCOVERY FOUNDATION =========="
