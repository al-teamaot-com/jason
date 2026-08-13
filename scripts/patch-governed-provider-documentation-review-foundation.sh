#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START GOVERNED PROVIDER DOCUMENTATION REVIEW FOUNDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: ADD REVIEW REQUEST CONTRACT =========="
cat > implementation/orchestrator/provider_documentation_review.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .provider_capability_discovery import ProviderCapabilityDiscoveryAssessment


@dataclass(frozen=True, slots=True)
class ProviderDocumentationReviewTarget:
    provider_id: str
    documentation_source: str
    unsupported_facts: tuple[str, ...]
    resource_authority: str | None = None
    connector_id: str | None = None

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "documentation_source": self.documentation_source,
            "unsupported_facts": self.unsupported_facts,
            "resource_authority": self.resource_authority,
            "connector_id": self.connector_id,
        }


@dataclass(frozen=True, slots=True)
class ProviderDocumentationReviewPlan:
    targets: tuple[ProviderDocumentationReviewTarget, ...]
    review_only: bool = True
    governance_owner: str = "technology-steward"
    interpretation_rule: str = (
        "Documented provider fields, schemas, and operations may be proposed as candidate evidence only. "
        "No semantic mapping, derivation, capability registration, provider selection, or execution authority "
        "is created by documentation review."
    )

    def as_context(self) -> Mapping[str, object]:
        return {
            "review_only": self.review_only,
            "governance_owner": self.governance_owner,
            "interpretation_rule": self.interpretation_rule,
            "targets": tuple(item.as_context() for item in self.targets),
        }


@dataclass(frozen=True, slots=True)
class GovernedProviderDocumentationReviewPlanner:
    """Turn registered-provider discovery into bounded documentation review targets.

    This planner does not fetch documentation, call providers, inspect credentials, infer mappings,
    or modify registries. It only creates the review workload that a governed documentation reader
    may later execute under Technology Steward authority.
    """

    def plan(
        self,
        *,
        discovery: ProviderCapabilityDiscoveryAssessment,
    ) -> ProviderDocumentationReviewPlan:
        targets: list[ProviderDocumentationReviewTarget] = []
        for candidate in discovery.candidates:
            for source in candidate.vendor_change_sources:
                source_text = str(source).strip()
                if not source_text:
                    continue
                targets.append(
                    ProviderDocumentationReviewTarget(
                        provider_id=candidate.provider_id,
                        documentation_source=source_text,
                        unsupported_facts=tuple(discovery.unsupported_facts),
                        resource_authority=candidate.resource_authority,
                        connector_id=candidate.connector_id,
                    )
                )
        targets.sort(
            key=lambda item: (
                item.provider_id.casefold(),
                item.documentation_source.casefold(),
            )
        )
        return ProviderDocumentationReviewPlan(targets=tuple(targets))
PY

echo "WROTE: implementation/orchestrator/provider_documentation_review.py"

echo "========== SECTION 3: ADD PROVIDER-NEUTRAL REGRESSION COVERAGE =========="
cat > implementation/orchestrator/tests/test_provider_documentation_review.py <<'PY'
from orchestrator.provider_capability_discovery import (
    ProviderCapabilityDiscoveryAssessment,
    ProviderCapabilityDiscoveryCandidate,
)
from orchestrator.provider_documentation_review import GovernedProviderDocumentationReviewPlanner


def test_discovery_candidates_become_review_only_documentation_targets():
    discovery = ProviderCapabilityDiscoveryAssessment(
        unsupported_facts=("example governed fact",),
        candidates=(
            ProviderCapabilityDiscoveryCandidate(
                provider_id="example_provider",
                display_name="Example Provider",
                registered_capabilities=("endpoint.device.search",),
                vendor_change_sources=("Example Provider API documentation",),
                technology_steward="technology-steward",
                resource_authority="managed_endpoint",
                connector_id="example_connector",
            ),
        ),
    )

    plan = GovernedProviderDocumentationReviewPlanner().plan(discovery=discovery)

    assert plan.review_only is True
    assert plan.governance_owner == "technology-steward"
    assert len(plan.targets) == 1
    target = plan.targets[0]
    assert target.provider_id == "example_provider"
    assert target.documentation_source == "Example Provider API documentation"
    assert target.unsupported_facts == ("example governed fact",)
    assert target.resource_authority == "managed_endpoint"
    assert target.connector_id == "example_connector"


def test_documentation_review_plan_does_not_claim_semantic_support():
    discovery = ProviderCapabilityDiscoveryAssessment(
        unsupported_facts=("unknown fact",),
        candidates=(
            ProviderCapabilityDiscoveryCandidate(
                provider_id="provider_a",
                display_name="Provider A",
                registered_capabilities=("resource.read",),
                vendor_change_sources=("Provider A docs", "Provider A schema"),
                technology_steward="technology-steward",
            ),
        ),
    )

    context = GovernedProviderDocumentationReviewPlanner().plan(discovery=discovery).as_context()

    assert context["review_only"] is True
    assert len(context["targets"]) == 2
    rule = str(context["interpretation_rule"])
    assert "candidate evidence only" in rule
    assert "No semantic mapping" in rule
PY

echo "WROTE: implementation/orchestrator/tests/test_provider_documentation_review.py"

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_provider_capability_discovery.py \
  implementation/orchestrator/tests/test_provider_documentation_review.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Governed provider documentation review planning foundation added and validated."
echo "Provider discovery can now be converted into bounded Technology Steward documentation-review targets."
echo "The foundation does not fetch documentation, call providers, inspect credentials, infer semantic mappings, mutate registries, or grant execution authority."
echo "NO RUNTIME WIRING PERFORMED."
echo "NO PROVIDER READ OR MUTATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED PROVIDER DOCUMENTATION REVIEW FOUNDATION =========="
