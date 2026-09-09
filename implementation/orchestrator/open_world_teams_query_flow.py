"""Open-world governed information-query front door for Teams.

Operational information is classified before the legacy Conversation Kernel.
The classification is explicitly independent of whether a requested field was
already known to Jason.

Information path:
  classify
  -> discover resources
  -> governed structural enrichment
  -> plan over discovered fields
  -> governed operational reads
  -> deterministic relational execution
  -> deterministic rendering

Ordinary conversation falls through unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
import traceback
from typing import Any

from usage_attribution.factories import human_attribution
from usage_attribution.runtime_context import bind_attribution_context

from .dynamic_conversation_kernel import (
    DynamicConversationContext,
)
from .open_world_discovery import (
    OpenWorldResourceDiscovery,
)
from .open_world_enrichment import (
    OpenWorldCatalogEnricher,
)
from .open_world_execution import (
    OpenWorldExecutionCoordinator,
)
from .open_world_query_planning import (
    OpenWorldQueryPlanner,
)
from .open_world_selector_grounding import (
    OpenWorldGroundedSelectorResolver,
)
from .open_world_semantic_mapping import (
    OpenWorldSemanticMapper,
)
from .teams_conversation_experience import (
    BoundTeamsConversationIntentExecutor,
    TeamsConversationExperienceResult,
)
from .teams_conversation_flow import (
    TeamsConversationRequest,
)
from .universal_teams_query_flow import (
    render_governed_query_result,
)


class OpenWorldUnsupportedInformation(
    RuntimeError
):
    pass


def _load_or_create_context(
    *,
    context_store,
    principal,
    identity,
) -> DynamicConversationContext:
    """Load bounded verified context without depending on a fallback implementation."""

    existing = context_store.get(
        organization_id=(
            principal.organization_id
        ),
        principal_id=(
            principal.principal_id
        ),
        conversation_id=(
            identity.conversation_id
        ),
    )

    if existing is not None:
        return existing

    return DynamicConversationContext(
        conversation_id=(
            identity.conversation_id
        ),
        principal_id=(
            principal.principal_id
        ),
        organization_id=(
            principal.organization_id
        ),
    )


@dataclass(frozen=True, slots=True)
class OpenWorldTeamsQueryFlow:
    # Generic composition contract. Runtime application layers may use this
    # marker to recognize that governed information handling is already fully
    # composed and must not be wrapped a second time.
    governed_information_front_door = True
    fallback: Any
    context_store: Any
    discovery: OpenWorldResourceDiscovery
    enricher: OpenWorldCatalogEnricher
    classifier: OpenWorldSemanticMapper
    selector_grounder: OpenWorldGroundedSelectorResolver
    planner: OpenWorldQueryPlanner
    coordinator: OpenWorldExecutionCoordinator

    def handle(
        self,
        request: TeamsConversationRequest,
    ) -> TeamsConversationExperienceResult:
        question = request.text.strip()

        if not question:
            return self.fallback.handle(
                request
            )

        stage = "resource_discovery"
        correlation_id = None
        executor = None

        try:
            base_catalog = (
                self.discovery.discover()
            )

            stage = "classification"

            classification = (
                self.classifier.map(
                    human_text=question,
                    catalog=base_catalog,
                )
            )

            if not classification.information_request:
                print(
                    "JASON_OPEN_WORLD_BYPASS"
                    + " reason=non_information",
                    file=sys.stderr,
                    flush=True,
                )

                return self.fallback.handle(
                    request
                )

            # Once classified as operational information, the request stays
            # on the governed information path. Missing fields or downstream
            # failures must never fall back into the old closed-world kernel.
            stage = "identity_binding"

            principal = (
                self.fallback.identity_binder.bind(
                    request.identity
                )
            )

            if principal is None:
                raise PermissionError(
                    "Teams identity is not bound to "
                    "a governed Jason principal"
                )

            stage = "correlation"

            correlation_id = (
                self.fallback.request_factory
                .new_correlation_id()
            )

            executor = (
                BoundTeamsConversationIntentExecutor(
                    request_factory=(
                        self.fallback.request_factory
                    ),
                    orchestrator=(
                        self.fallback.orchestrator
                    ),
                    principal=principal,
                    identity=request.identity,
                    correlation_id=correlation_id,
                )
            )

            attribution = human_attribution(
                organization_id=principal.organization_id,
                correlation_id=correlation_id,
                request_id=request.identity.message_id,
                principal_id=principal.principal_id,
                source_channel="teams",
                purpose="Resolve governed operational information",
                capability="conversation.reason",
                client_id=principal.client_id,
                email_address=principal.email_address,
                workflow_id=request.identity.conversation_id,
            )

            # Accounting/trace context only. This scope is established after Jason
            # identity binding and never participates in authority or provider choice.
            with bind_attribution_context(attribution):
                stage = "selector_grounding"

                context = _load_or_create_context(
                    context_store=self.context_store,
                    principal=principal,
                    identity=request.identity,
                )

                grounding = (
                    self.selector_grounder.ground(
                        human_text=question,
                        context=context,
                        catalog=base_catalog,
                    )
                )

                stage = "structural_enrichment"

                catalog = self.enricher.enrich(
                    catalog=grounding.catalog,
                    executor=executor,
                    selector_references=(
                        dict(
                            grounding.enrichment_selectors
                        )
                    ),
                )

                stage = "query_planning"

                plan = self.planner.plan(
                    human_text=question,
                    catalog=catalog,
                )

                stage = "selector_binding"

                plan = (
                    self.selector_grounder.bind_plan(
                        plan=plan,
                        catalog=catalog,
                        selectors_by_handle=(
                            grounding.selectors_by_handle
                        ),
                    )
                )

                stage = "governed_execution"

                execution = (
                    self.coordinator.execute(
                        plan=plan,
                        catalog=catalog,
                        executor=executor,
                    )
                )

                stage = "deterministic_rendering"

                response_text = (
                    render_governed_query_result(
                        result=(
                            execution.query_result
                        ),
                        answer_mode=(
                            plan.answer_mode
                        ),
                    )
                )

                orchestrations = tuple(
                    execution.orchestrations
                )

            print(
                "JASON_OPEN_WORLD_SUCCESS"
                + " correlation_id="
                + str(correlation_id)
                + " sources="
                + str(len(plan.sources))
                + " joins="
                + str(
                    len(
                        plan.relational_plan.joins
                    )
                )
                + " rows="
                + str(
                    len(
                        execution.query_result.rows
                    )
                )
                + " columns="
                + str(
                    len(
                        execution.query_result.columns
                    )
                )
                + " answer_mode="
                + str(plan.answer_mode),
                file=sys.stderr,
                flush=True,
            )

        except Exception as error:
            # Generic operational observability. Never emit question text,
            # provider credentials, evidence values, or connector secrets.
            error_correlation = (
                correlation_id
                or "unassigned"
            )

            print(
                "JASON_OPEN_WORLD_FAILURE"
                + " stage="
                + stage
                + " exception="
                + type(error).__name__
                + " correlation_id="
                + str(error_correlation),
                file=sys.stderr,
                flush=True,
            )

            traceback.print_exc(
                file=sys.stderr,
            )

            response_text = (
                "Jason could not establish that information "
                "from the currently available governed evidence."
            )

            orchestrations = (
                tuple(executor.results)
                if executor is not None
                else tuple()
            )

            if correlation_id is None:
                correlation_id = (
                    self.fallback.request_factory
                    .new_correlation_id()
                )

        message_id = (
            self.fallback.transport.send(
                conversation_id=(
                    request.identity.conversation_id
                ),
                text=response_text,
                correlation_id=(
                    correlation_id
                ),
            )
        )

        return TeamsConversationExperienceResult(
            response_text=response_text,
            transport_message_id=str(
                message_id
            ),
            correlation_id=correlation_id,
            orchestrations=orchestrations,
        )
