from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from kernel.capabilities import CapabilityDefinition

from .resource_inquiry import ResourceInquiry, ResourcePlanStep
from .semantic_mapping_registry import SemanticMappingRegistry


_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower()))


def _csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


@dataclass(frozen=True, slots=True)
class MetadataResourceCapabilityReasoner:
    """Choose reusable read capabilities from governed metadata, not hard-coded workflows.

    This reasoner has no provider handles, credentials, network access, or execution
    authority. It compares the resource selector and requested facts with capability
    metadata. The planner revalidates its selection before orchestration.

    It is deliberately generic: adding a new field to a provider does not require a
    new script. Technology stewardship updates capability metadata when provider
    coverage changes, and the same reasoner can select the broader capability.
    """

    minimum_score: int = 1
    semantic_mapping_registry: SemanticMappingRegistry | None = None

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

        requested_text = " ".join(
            inquiry.requested_facts
        )
        requested_tokens = _tokens(
            requested_text
        )
        requested_phrases = {
            " ".join(
                _TOKEN.findall(
                    str(fact).casefold()
                )
            )
            for fact in inquiry.requested_facts
            if str(fact).strip()
        }

        ranked: list[
            tuple[
                int,
                str,
                CapabilityDefinition,
            ]
        ] = []

        for capability in candidates:
            metadata = capability.metadata

            supported_selectors = _csv(
                metadata.get(
                    "selector_keys",
                    "",
                )
            )

            # Every supplied selector must be declared by the capability.
            # This prevents a grounded endpoint hostname from being
            # reinterpreted as software, site, user, or unrelated scope.
            if (
                selector_keys
                and not selector_keys.issubset(
                    supported_selectors
                )
            ):
                continue

            operation = metadata.get(
                "operation",
                "",
            ).strip().lower()

            declared_facts = {
                " ".join(
                    _TOKEN.findall(
                        item.casefold()
                    )
                )
                for item in _csv(
                    metadata.get(
                        "canonical_facts",
                        "",
                    )
                )
                if item.strip()
            }

            exact_fact_coverage = len(
                requested_phrases.intersection(
                    declared_facts
                )
            )

            searchable_text = " ".join(
                (
                    capability.display_name,
                    capability.business_purpose,
                    metadata.get(
                        "fact_hints",
                        "",
                    ),
                    metadata.get(
                        "planning_guidance",
                        "",
                    ),
                )
            )

            capability_tokens = _tokens(
                searchable_text
            )

            selector_overlap = len(
                selector_keys.intersection(
                    supported_selectors
                )
            )
            fact_overlap = len(
                requested_tokens.intersection(
                    capability_tokens
                )
            )

            score = (
                selector_overlap * 6
                + exact_fact_coverage * 50
                + fact_overlap
            )

            # Approved mappings remain governed coverage evidence.
            if self.semantic_mapping_registry is not None:
                for requested_fact in inquiry.requested_facts:
                    approved = (
                        self.semantic_mapping_registry.find_active(
                            canonical_fact=requested_fact,
                        )
                    )

                    if any(
                        capability.capability_name
                        in mapping.capability_names
                        for mapping in approved
                    ):
                        score += 20

            if (
                "resource_id" in selector_keys
                and operation == "read"
            ):
                score += 8

            elif (
                "resource_id" not in selector_keys
                and operation == "search"
            ):
                score += 4

            ranked.append(
                (
                    score,
                    capability.capability_name,
                    capability,
                )
            )

        if not ranked:
            return ()

        ranked.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )

        score, _, selected = ranked[0]

        if score < self.minimum_score:
            return ()

        arguments = {
            **dict(inquiry.resource_selector),
            "requested_facts":
                inquiry.requested_facts,
            "result_intent":
                inquiry.result_intent,
            "completeness_requirement":
                inquiry.completeness_requirement,
        }

        if inquiry.evidence_contexts:
            arguments["evidence_contexts"] = {
                fact: tuple(contexts)
                for fact, contexts
                in inquiry.evidence_contexts.items()
            }

        if inquiry.relationship_type:
            arguments["relationship_type"] = (
                inquiry.relationship_type
            )

        if (
            inquiry.temporal_semantics
            != "unspecified"
        ):
            arguments["temporal_semantics"] = (
                inquiry.temporal_semantics
            )

        return (
            ResourcePlanStep(
                capability_name=
                    selected.capability_name,
                arguments=arguments,
                purpose=(
                    "retrieve governed evidence through the read capability "
                    "whose declared semantic coverage satisfies the request"
                ),
            ),
        )
