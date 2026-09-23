"""Ground selector-only open-world resources using Jason's existing binder.

The language model receives no provider identity and cannot manufacture a selector.
A selector value must survive GroundedConversationIntentBuilder validation, which
permits only exact human-message literals or verified conversation entities.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from .dynamic_conversation_intent import (
    DynamicIntentBindingError,
    GroundedConversationIntentBuilder,
)
from .dynamic_conversation_kernel import (
    DynamicCapabilityRequirement,
    DynamicConversationContext,
    DynamicConversationPlan,
    OfferedConversationCapability,
)
from .open_world_query_planning import (
    OpenWorldQueryPlan,
)
from .open_world_schema import (
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)
from .teams_conversation_flow import (
    ConversationIntent,
)


class OpenWorldSelectorGroundingError(
    RuntimeError
):
    pass


@dataclass(frozen=True, slots=True)
class OpenWorldSelectorGrounding:
    catalog: OpenWorldResourceCatalog
    enrichment_selectors: Mapping[
        tuple[str, str],
        str,
    ]
    selectors_by_handle: Mapping[
        str,
        str,
    ]


@dataclass(frozen=True, slots=True)
class OpenWorldGroundedSelectorResolver:
    builder: GroundedConversationIntentBuilder

    def ground(
        self,
        *,
        human_text: str,
        context: DynamicConversationContext,
        catalog: OpenWorldResourceCatalog,
    ) -> OpenWorldSelectorGrounding:
        eligible = []
        enrichment_selectors = {}
        selectors_by_handle = {}

        active_entity_refs = tuple(
            dict.fromkeys(
                str(ref)
                for ref
                in context.active_entity_refs.values()
                if str(ref).strip()
            )
        )

        grouped = {}

        for resource in catalog.resources:
            # Collection resources are always executable. If they also expose
            # selector keys, they participate in the same safe grounding pass
            # so an explicit human selector can narrow the governed search.
            if resource.collection_supported:
                eligible.append(
                    resource
                )

            key = (
                resource.resource_type,
                tuple(
                    resource.selector_keys
                ),
            )

            if not resource.selector_keys:
                continue

            grouped.setdefault(
                key,
                [],
            ).append(
                resource
            )

        for (
            resource_type,
            selector_keys,
        ), resources in grouped.items():
            if not selector_keys:
                continue

            representative = resources[0]

            capability = (
                OfferedConversationCapability(
                    capability_id=(
                        representative.resource_handle
                    ),
                    description=(
                        "Ground one selector for governed "
                        f"resource type {resource_type}."
                    ),
                    provider=None,
                    input_schema={
                        "selector_keys": (
                            selector_keys
                        ),
                        "selector_source_policy": {
                            key: policy
                            for key, policy
                            in representative.selector_source_policy
                        },
                    },
                    output_schema={},
                    permission_mode="observe",
                    risk="low",
                )
            )

            plan = DynamicConversationPlan(
                outcome="plan",
                requirements=(
                    DynamicCapabilityRequirement(
                        capability_id=(
                            representative.resource_handle
                        ),
                        purpose=human_text,
                        entity_refs=(
                            active_entity_refs
                        ),
                    ),
                ),
            )

            try:
                intent = self.builder.build(
                    text=human_text,
                    context=context,
                    plan=plan,
                    capabilities=(
                        capability,
                    ),
                )
            except DynamicIntentBindingError:
                # A candidate resource whose selector cannot be safely
                # grounded is simply ineligible for this turn. One rejected
                # candidate must not abort other independently executable
                # governed resources.
                continue

            if not isinstance(
                intent,
                ConversationIntent,
            ):
                continue

            grounded_values = tuple(
                dict.fromkeys(
                    str(
                        intent.arguments[
                            key
                        ]
                    ).strip()
                    for key in selector_keys
                    if (
                        key in intent.arguments
                        and str(
                            intent.arguments[
                                key
                            ]
                        ).strip()
                    )
                )
            )

            # The current open-world read contract carries one provider-neutral
            # selector reference. Multiple grounded values are therefore
            # ambiguous and must fail closed rather than being combined.
            if len(
                grounded_values
            ) != 1:
                continue

            selector = (
                grounded_values[0]
            )

            for resource in resources:
                if not resource.collection_supported:
                    eligible.append(
                        resource
                    )

                selectors_by_handle[
                    resource.resource_handle
                ] = selector

                enrichment_selectors[
                    (
                        resource.resource_type,
                        resource.capability_name,
                    )
                ] = selector

        if not eligible:
            raise OpenWorldSelectorGroundingError(
                "no executable governed resources "
                "are available for this information turn"
            )

        return OpenWorldSelectorGrounding(
            catalog=OpenWorldResourceCatalog(
                resources=tuple(
                    eligible
                )
            ),
            enrichment_selectors=(
                enrichment_selectors
            ),
            selectors_by_handle=(
                selectors_by_handle
            ),
        )

    def bind_plan(
        self,
        *,
        plan: OpenWorldQueryPlan,
        catalog: OpenWorldResourceCatalog,
        selectors_by_handle: Mapping[
            str,
            str,
        ],
    ) -> OpenWorldQueryPlan:
        resources = {
            resource.resource_handle: resource
            for resource in catalog.resources
        }

        bound_sources = []

        for source in plan.sources:
            resource = resources.get(
                source.resource_handle
            )

            if resource is None:
                raise OpenWorldSelectorGroundingError(
                    "planned resource is not "
                    "eligible for this turn"
                )

            selector = (
                selectors_by_handle.get(
                    source.resource_handle
                )
            )

            if (
                not resource.collection_supported
                and not (
                    selector
                    or ""
                ).strip()
            ):
                raise OpenWorldSelectorGroundingError(
                    "selector-only planned resource "
                    "has no grounded selector"
                )

            bound_sources.append(
                replace(
                    source,
                    selector_reference=(
                        selector
                    ),
                )
            )

        return replace(
            plan,
            sources=tuple(
                bound_sources
            ),
        )
