from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from kernel.capabilities import CapabilityDefinition

from .resource_inquiry import ResourceInquiry, ResourcePlanStep


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

    def select(
        self,
        *,
        inquiry: ResourceInquiry,
        candidates: Sequence[CapabilityDefinition],
    ) -> Sequence[ResourcePlanStep]:
        selector_keys = {str(key).strip() for key in inquiry.resource_selector if str(key).strip()}
        requested_text = " ".join(inquiry.requested_facts)
        requested_tokens = _tokens(requested_text)

        ranked: list[tuple[int, str, CapabilityDefinition]] = []
        for capability in candidates:
            metadata = capability.metadata
            supported_selectors = _csv(metadata.get("selector_keys", ""))
            operation = metadata.get("operation", "").strip().lower()
            searchable_text = " ".join(
                (
                    capability.display_name,
                    capability.business_purpose,
                    metadata.get("fact_hints", ""),
                    metadata.get("planning_guidance", ""),
                )
            )
            capability_tokens = _tokens(searchable_text)

            selector_overlap = len(selector_keys.intersection(supported_selectors))
            fact_overlap = len(requested_tokens.intersection(capability_tokens))
            score = selector_overlap * 6 + fact_overlap

            # Generic resource-planning preference: use direct read when a durable
            # resource_id is already known; otherwise prefer search for selectors.
            if "resource_id" in selector_keys and operation == "read":
                score += 8
            elif "resource_id" not in selector_keys and operation == "search":
                score += 4

            ranked.append((score, capability.capability_name, capability))

        if not ranked:
            return ()

        ranked.sort(key=lambda item: (-item[0], item[1]))
        score, _, selected = ranked[0]
        if score < self.minimum_score:
            return ()

        return (
            ResourcePlanStep(
                capability_name=selected.capability_name,
                arguments={
                    **dict(inquiry.resource_selector),
                    "requested_facts": inquiry.requested_facts,
                },
                purpose=(
                    "retrieve the governed resource record most likely to contain "
                    "the requested facts"
                ),
            ),
        )
