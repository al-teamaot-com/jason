"""Progressive backend expansion when primary governed evidence is insufficient.

A weak reasoning model is allowed to choose an imperfect *order* for specialized reads,
but it cannot fan out, change the target, invent a provider, or make an unsupported
answer true. Jason attempts at most one additional governed resource at a time and
re-evaluates evidence before considering another. This trades backend latency for
cost/control while keeping the human experience and correctness contract stable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .conversation_kernel import InformationNeed, ValidatedReasoningPool
from .information_fulfillment import (
    FulfillmentCapability,
    FulfillmentStep,
    RegistryBackedFulfillmentCatalog,
)


class EvidenceGapFulfillmentError(ValueError):
    """A bounded specialized-resource selection was invalid."""


@dataclass(frozen=True, slots=True)
class EvidenceGapFulfillmentPlanner:
    """Choose one untried specialized resource, never speculative fan-out."""

    catalog: RegistryBackedFulfillmentCatalog
    reasoning: ValidatedReasoningPool

    def next_step(
        self,
        *,
        need: InformationNeed,
        attempted_capabilities: tuple[str, ...],
    ) -> FulfillmentStep | None:
        if need.authority != "observe":
            raise PermissionError(
                "evidence-gap fulfillment is read-only"
            )
        attempted = {item.strip() for item in attempted_capabilities if item.strip()}
        candidates = tuple(
            item
            for item in self.catalog.for_resource(need.target.kind)
            if item.permission_mode == "observe"
            and item.role == "specialized"
            and item.operation in {"search", "read"}
            and item.capability_name not in attempted
        )
        if not candidates:
            return None

        selected_name, _ = self.reasoning.complete_validated(
            system=(
                "You are Jason's bounded backend evidence-gap planner. The human "
                "target and information need are already fixed, and the primary governed "
                "resource was insufficient. Each offered candidate is an authorized "
                "provider-neutral read, but availability does not imply relevance. "
                "Choose one candidate only when its governed description makes it a "
                "plausible source for establishing the missing information. If none of "
                "the offered capabilities plausibly covers the missing information, "
                "choose __none__. Do not speculate from resource type alone. Do not "
                "change the target, information need, authority, provider, connector, "
                "or API operation. Return only the required object."
            ),
            user=json.dumps(
                {
                    "target_kind": need.target.kind,
                    "information_need": need.need,
                    "temporal_scope": need.temporal_scope,
                    "completeness": need.completeness,
                    "candidates": [
                        {
                            "capability_name": item.capability_name,
                            "description": item.description,
                            "resource_types": list(item.resource_types),
                            "operation": item.operation,
                        }
                        for item in candidates
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["capability_name"],
                "properties": {
                    "capability_name": {
                        "type": "string",
                        "enum": [
                            "__none__",
                            *[
                                item.capability_name
                                for item in candidates
                            ],
                        ],
                    }
                },
            },
            max_output_tokens=64,
            validator=lambda proposal: _validate_choice(
                proposal=proposal,
                candidates=candidates,
            ),
        )

        if selected_name is None:
            return None

        selected = next(
            item
            for item in candidates
            if item.capability_name == selected_name
        )

        return FulfillmentStep(
            capability_name=selected.capability_name,
            target_reference=need.target.reference,
            target_source=need.target.source,
            information_need=need.need,
            authority=need.authority,
        )


def _validate_choice(
    *,
    proposal: Mapping[str, Any],
    candidates: tuple[FulfillmentCapability, ...],
) -> str | None:
    if not isinstance(proposal, Mapping) or set(proposal) != {"capability_name"}:
        raise EvidenceGapFulfillmentError(
            "evidence-gap proposal shape is invalid"
        )

    name = str(
        proposal.get(
            "capability_name",
            "",
        )
    ).strip()

    if name == "__none__":
        return None

    allowed = {
        item.capability_name
        for item in candidates
    }

    if name not in allowed:
        raise EvidenceGapFulfillmentError(
            "evidence-gap proposal selected an unoffered capability"
        )

    return name
