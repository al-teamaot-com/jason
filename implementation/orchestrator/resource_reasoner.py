from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from kernel.capabilities import CapabilityDefinition

from .resource_inquiry import ResourceInquiry, ResourcePlanStep
from .semantic_capability_coverage import semantic_resolution_matches_resource_contract
from .semantic_fact_resolver import (
    DEFAULT_SEMANTIC_FACT_RESOLVER,
    SemanticFactResolver,
)
from .semantic_mapping_registry import SemanticMappingRegistry


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower()))


def _csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _normalized_fact(value: str) -> str:
    return " ".join(_TOKEN.findall(value.casefold()))


@dataclass(frozen=True, slots=True)
class MetadataResourceCapabilityReasoner:
    """Choose reusable read capabilities from governed metadata, not hard-coded workflows.

    This reasoner has no provider handles, credentials, network access, or execution
    authority. It compares the resource selector and requested facts with capability
    metadata. The planner revalidates its selection before orchestration.

    Governed Semantic Knowledge Registry concepts may establish resource-domain
    coverage structurally through concept namespace/evidence context plus capability
    ``resource_types``. This is not phrase-to-provider mapping and does not authorize
    execution; it only prevents a growing static list of fact labels from becoming the
    capability-selection contract.
    """

    minimum_score: int = 1
    semantic_mapping_registry: SemanticMappingRegistry | None = None
    fact_resolver: SemanticFactResolver | None = DEFAULT_SEMANTIC_FACT_RESOLVER

    def select(
        self,
        *,
        inquiry: ResourceInquiry,
        candidates: Sequence[CapabilityDefinition],
    ) -> Sequence[ResourcePlanStep]:
        selector_keys = {
            str(key).strip()
            for key in inquiry.resource_selector
            if str(key).strip()
        }

        requested_text = " ".join(inquiry.requested_facts)
        requested_tokens = _tokens(requested_text)
        normalized_requested = tuple(
            (fact, _normalized_fact(str(fact)))
            for fact in inquiry.requested_facts
            if str(fact).strip()
        )
        requested_phrases = {
            normalized
            for _, normalized in normalized_requested
            if normalized
        }

        semantic_resolutions = []
        governed_semantic_requested: set[str] = set()
        if self.fact_resolver is not None:
            for original, normalized in normalized_requested:
                resolution = self.fact_resolver.resolve(str(original))
                if resolution is None:
                    continue
                semantic_resolutions.append((original, normalized, resolution))
                if (
                    resolution.source == "semantic_knowledge_registry"
                    and normalized
                ):
                    governed_semantic_requested.add(normalized)

        ranked: list[
            tuple[
                int,
                str,
                CapabilityDefinition,
                frozenset[str],
            ]
        ] = []

        for capability in candidates:
            metadata = capability.metadata

            supported_selectors = _csv(
                metadata.get("selector_keys", "")
            )

            # Every supplied selector must be declared by the capability.
            # This prevents a grounded endpoint hostname from being
            # reinterpreted as software, site, user, or unrelated scope.
            if selector_keys and not selector_keys.issubset(supported_selectors):
                continue

            operation = metadata.get("operation", "").strip().lower()

            declared_facts = {
                _normalized_fact(item)
                for item in _csv(metadata.get("canonical_facts", ""))
                if item.strip()
            }

            # Transitional collection metadata remains governed coverage for
            # collection-oriented capabilities while semantic resource contracts
            # replace fact-by-fact canonical lists.
            collection_fact = str(metadata.get("collection_fact", "")).strip()
            if collection_fact:
                declared_facts.add(_normalized_fact(collection_fact))

            governed_coverage = set(
                requested_phrases.intersection(declared_facts)
            )

            # Structural semantic coverage is derived from governed concept/resource
            # metadata rather than from a manually maintained phrase or fact mapping.
            for _, normalized_fact, resolution in semantic_resolutions:
                if not normalized_fact:
                    continue
                if semantic_resolution_matches_resource_contract(
                    resolution=resolution,
                    metadata=metadata,
                ):
                    governed_coverage.add(normalized_fact)

            searchable_text = " ".join(
                (
                    capability.display_name,
                    capability.business_purpose,
                    metadata.get("fact_hints", ""),
                    metadata.get("planning_guidance", ""),
                )
            )

            capability_tokens = _tokens(searchable_text)

            selector_overlap = len(
                selector_keys.intersection(supported_selectors)
            )
            fact_overlap = len(
                requested_tokens.intersection(capability_tokens)
            )

            mapped_coverage: set[str] = set()

            # Approved mappings remain a transitional governed compatibility path.
            # New semantic coverage must use structural semantic/resource contracts.
            if self.semantic_mapping_registry is not None:
                for requested_fact, normalized_fact in normalized_requested:
                    approved = self.semantic_mapping_registry.find_active(
                        canonical_fact=requested_fact,
                    )

                    if any(
                        capability.capability_name in mapping.capability_names
                        for mapping in approved
                    ):
                        mapped_coverage.add(normalized_fact)

            governed_coverage.update(mapped_coverage)
            frozen_coverage = frozenset(governed_coverage)

            score = (
                selector_overlap * 6
                + len(frozen_coverage) * 50
                + fact_overlap
            )

            if "resource_id" in selector_keys and operation == "read":
                score += 8
            elif "resource_id" not in selector_keys and operation == "search":
                score += 4

            ranked.append(
                (
                    score,
                    capability.capability_name,
                    capability,
                    frozen_coverage,
                )
            )

        if not ranked:
            return ()

        if governed_semantic_requested:
            available_governed_coverage: set[str] = set()
            for _, _, _, coverage in ranked:
                available_governed_coverage.update(coverage)
            if not governed_semantic_requested.issubset(
                available_governed_coverage
            ):
                return ()

        ranked.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )

        # A multi-fact read may require more than one reusable capability. Split
        # the request only when governed structural semantics, transitional canonical
        # metadata, governed collection facts, or approved mappings account for every
        # requested fact. Partial semantic guesses remain fail-closed.
        if len(normalized_requested) > 1:
            requested_set = {
                normalized
                for _, normalized in normalized_requested
                if normalized
            }
            available_coverage: set[str] = set()
            for _, _, _, coverage in ranked:
                available_coverage.update(coverage)

            if requested_set and requested_set.issubset(available_coverage):
                uncovered = set(requested_set)
                steps: list[ResourcePlanStep] = []

                while uncovered:
                    covering = [
                        item
                        for item in ranked
                        if item[3].intersection(uncovered)
                    ]
                    if not covering:
                        return ()

                    covering.sort(
                        key=lambda item: (
                            -len(item[3].intersection(uncovered)),
                            -item[0],
                            item[1],
                        )
                    )
                    score, _, selected, coverage = covering[0]
                    if score < self.minimum_score:
                        return ()

                    assigned = coverage.intersection(uncovered)
                    assigned_facts = tuple(
                        original
                        for original, normalized in normalized_requested
                        if normalized in assigned
                    )
                    steps.append(
                        self._plan_step(
                            inquiry=inquiry,
                            selected=selected,
                            requested_facts=assigned_facts,
                        )
                    )
                    uncovered.difference_update(assigned)

                return tuple(steps)

        score, _, selected, _ = ranked[0]

        if score < self.minimum_score:
            return ()

        return (
            self._plan_step(
                inquiry=inquiry,
                selected=selected,
                requested_facts=inquiry.requested_facts,
            ),
        )

    @staticmethod
    def _plan_step(
        *,
        inquiry: ResourceInquiry,
        selected: CapabilityDefinition,
        requested_facts: tuple[str, ...],
    ) -> ResourcePlanStep:
        arguments = {
            **dict(inquiry.resource_selector),
            "requested_facts": requested_facts,
            "result_intent": inquiry.result_intent,
            "completeness_requirement": inquiry.completeness_requirement,
        }

        if inquiry.evidence_contexts:
            step_contexts = {
                fact: tuple(contexts)
                for fact, contexts in inquiry.evidence_contexts.items()
                if fact in requested_facts
            }
            if step_contexts:
                arguments["evidence_contexts"] = step_contexts

        if inquiry.relationship_type:
            arguments["relationship_type"] = inquiry.relationship_type

        if inquiry.temporal_semantics != "unspecified":
            arguments["temporal_semantics"] = inquiry.temporal_semantics

        return ResourcePlanStep(
            capability_name=selected.capability_name,
            arguments=arguments,
            purpose=(
                "retrieve governed evidence through the read capability "
                "whose governed semantic/resource coverage satisfies the request"
            ),
        )
