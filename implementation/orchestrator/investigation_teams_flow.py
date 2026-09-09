"""Opt-in Teams cutover for Jason's generic investigation loop.

Ordinary conversation and genuine human clarification continue through the
existing Conversation Experience unchanged. Information turns use the new
generic broker-driven investigation loop while preserving the same authenticated
Teams identity, request factory, Central Orchestrator, and transport.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dynamic_conversation_kernel import (
    DynamicConversationContext,
)
from .investigation_answer import (
    InvestigationAnswerer,
)
from .simple_reasoning_loop import (
    SimpleReasoningLoop,
)
from .investigation_turn_router import (
    InvestigationTurnKind,
    InvestigationTurnRouter,
)
from .teams_conversation_experience import (
    BoundTeamsConversationIntentExecutor,
    TeamsConversationExperienceFlow,
    TeamsConversationExperienceResult,
)
from .teams_conversation_flow import (
    TeamsConversationRequest,
)


@dataclass(frozen=True, slots=True)
class InvestigationTeamsConversationFlow:
    fallback: TeamsConversationExperienceFlow
    investigation: SimpleReasoningLoop
    answerer: InvestigationAnswerer
    router: InvestigationTurnRouter

    def handle(
        self,
        request: TeamsConversationRequest,
    ) -> TeamsConversationExperienceResult:
        try:
            principal = self.fallback.identity_binder.bind(
                request.identity
            )
        except Exception as exc:
            print(
                "JASON_INVESTIGATION_FAILURE "
                "stage=identity_binding "
                f"exception={type(exc).__name__} "
                f"detail={exc}",
                flush=True,
            )
            raise

        if principal is None:
            raise PermissionError(
                "Teams identity is not bound to a governed Jason principal"
            )

        try:
            context = self._load_or_create(
                principal=principal,
                request=request,
            )
        except Exception as exc:
            print(
                "JASON_INVESTIGATION_FAILURE "
                "stage=context_load "
                f"exception={type(exc).__name__} "
                f"detail={exc}",
                flush=True,
            )
            raise

        # The simple read path does not use a semantic turn router.
        # Actions are intentionally not part of this proving change.

        correlation_id = (
            self.fallback.request_factory
            .new_correlation_id()
        )

        executor = BoundTeamsConversationIntentExecutor(
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

        try:
            result = self.investigation.run(
                human_text=request.text.strip(),
                context=context,
                executor=executor,
            )
        except Exception as exc:
            print(
                "JASON_INVESTIGATION_FAILURE "
                "stage=investigation_loop "
                f"exception={type(exc).__name__} "
                f"detail={exc} "
                f"correlation_id={correlation_id}",
                flush=True,
            )
            raise

        response_text = result.answer_text

        response_text = response_text.strip()

        if not response_text:
            raise RuntimeError(
                "investigation produced empty response"
            )

        transport_message_id = (
            self.fallback.transport.send(
                conversation_id=(
                    request.identity.conversation_id
                ),
                text=response_text,
                correlation_id=correlation_id,
            )
        )

        if not transport_message_id.strip():
            raise RuntimeError(
                "Teams transport did not return a message identifier"
            )

        if (
            result.context != context
        ):
            self.fallback.context_store.put(
                result.context
            )

        return TeamsConversationExperienceResult(
            response_text=response_text,
            transport_message_id=(
                transport_message_id.strip()
            ),
            correlation_id=correlation_id,
            orchestrations=tuple(
                executor.results
            ),
        )

    def _load_or_create(
        self,
        *,
        principal,
        request,
    ) -> DynamicConversationContext:
        existing = self.fallback.context_store.get(
            organization_id=(
                principal.organization_id
            ),
            principal_id=(
                principal.principal_id
            ),
            conversation_id=(
                request.identity.conversation_id
            ),
        )

        if existing is not None:
            return existing

        return DynamicConversationContext(
            conversation_id=(
                request.identity.conversation_id
            ),
            principal_id=(
                principal.principal_id
            ),
            organization_id=(
                principal.organization_id
            ),
        )
