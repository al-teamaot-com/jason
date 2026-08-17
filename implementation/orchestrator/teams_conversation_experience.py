"""First-class Teams adapter for Jason's model-independent Conversation Experience.

Teams remains intentionally thin. Identity is bound first, the Conversation Kernel owns
human meaning, every read crosses the Central Orchestrator, and exactly one quality-gated
human response is delivered for the turn. Backend model retries, progressive resource
reads, provider identities, and orchestration details are not transport semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .conversation_experience import ConversationExperienceCoordinator
from .conversation_text_quality import ConversationTextQualityGate
from .contracts import OrchestrationRequest, OrchestrationResult
from .dynamic_conversation_kernel import DynamicConversationContext
from .progressive_conversation_read import ProgressiveConversationReadEngine
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    TeamsConversationIdentityBinder,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
    TeamsConversationTransport,
)


class ConversationContextStore(Protocol):
    def get(
        self,
        *,
        organization_id: str,
        principal_id: str,
        conversation_id: str,
    ) -> DynamicConversationContext | None: ...

    def put(self, context: DynamicConversationContext) -> DynamicConversationContext: ...


class ConversationRequestFactory(Protocol):
    def new_correlation_id(self) -> str: ...

    def build(
        self,
        *,
        principal: BoundConversationPrincipal,
        intent: ConversationIntent,
        identity: TeamsConversationPrincipalEvidence,
        correlation_id: str,
    ) -> OrchestrationRequest: ...


class ConversationOrchestrator(Protocol):
    def execute(self, request: OrchestrationRequest) -> OrchestrationResult: ...


@dataclass(frozen=True, slots=True)
class TeamsConversationExperienceResult:
    response_text: str
    transport_message_id: str
    correlation_id: str
    orchestrations: tuple[OrchestrationResult, ...] = ()

    def __post_init__(self) -> None:
        if not self.response_text.strip():
            raise ValueError("Teams conversation experience response is required")
        if not self.transport_message_id.strip():
            raise ValueError("Teams transport message id is required")
        if not self.correlation_id.strip():
            raise ValueError("Teams conversation correlation id is required")

    @property
    def orchestration_status(self) -> str:
        """Summarize backend execution without inventing an orchestration for chat-only turns."""
        if not self.orchestrations:
            return "not_required"
        statuses = tuple(item.status.value for item in self.orchestrations)
        if len(set(statuses)) == 1:
            return statuses[0]
        if "succeeded" in statuses:
            return "partial"
        return statuses[-1]


class BoundTeamsConversationIntentExecutor:
    """Bind progressive read intents to one authenticated Teams turn/correlation scope."""

    def __init__(
        self,
        *,
        request_factory: ConversationRequestFactory,
        orchestrator: ConversationOrchestrator,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
        correlation_id: str,
    ) -> None:
        self.request_factory = request_factory
        self.orchestrator = orchestrator
        self.principal = principal
        self.identity = identity
        self.correlation_id = correlation_id
        self.results: list[OrchestrationResult] = []

    def execute(self, intent: ConversationIntent) -> OrchestrationResult:
        request = self.request_factory.build(
            principal=self.principal,
            intent=intent,
            identity=self.identity,
            correlation_id=self.correlation_id,
        )
        self._validate(request=request, intent=intent)
        result = self.orchestrator.execute(request)
        if result.correlation_id != self.correlation_id:
            raise PermissionError(
                "Central Orchestrator result changed the Teams turn correlation identity"
            )
        if result.capability_name != intent.capability_name:
            raise PermissionError(
                "Central Orchestrator result does not match the governed conversation intent"
            )
        self.results.append(result)
        return result

    def _validate(
        self,
        *,
        request: OrchestrationRequest,
        intent: ConversationIntent,
    ) -> None:
        if request.correlation_id != self.correlation_id:
            raise PermissionError("request factory changed the Teams turn correlation identity")
        if request.principal_id != self.principal.principal_id:
            raise PermissionError("request factory changed the bound Teams principal")
        if request.organization_id != self.principal.organization_id:
            raise PermissionError("request factory changed the bound Teams organization")
        if request.client_id != self.principal.client_id:
            raise PermissionError("request factory changed the bound Teams client")
        if request.capability_name != intent.capability_name:
            raise PermissionError("request factory changed the governed capability intent")
        if request.requested_mode != intent.execution_mode:
            raise PermissionError("request factory changed the governed execution mode")
        if request.permission_mode != intent.permission_mode:
            raise PermissionError("request factory changed the governed permission mode")
        if request.requester_kind != "human":
            raise PermissionError("Teams conversation must retain human requester identity")


@dataclass(frozen=True, slots=True)
class TeamsConversationExperienceFlow:
    """Deliver one authenticated, quality-gated Jason turn through Teams."""

    identity_binder: TeamsConversationIdentityBinder
    context_store: ConversationContextStore
    experience: ConversationExperienceCoordinator
    progressive_reads: ProgressiveConversationReadEngine
    request_factory: ConversationRequestFactory
    orchestrator: ConversationOrchestrator
    text_quality: ConversationTextQualityGate
    transport: TeamsConversationTransport

    def handle(self, request: TeamsConversationRequest) -> TeamsConversationExperienceResult:
        principal = self.identity_binder.bind(request.identity)
        if principal is None:
            raise PermissionError(
                "Teams identity is not bound to a governed Jason principal"
            )

        context = self._load_or_create(principal=principal, identity=request.identity)
        resolution = self.experience.resolve(
            text=request.text.strip(),
            context=context,
        )
        self.context_store.put(resolution.context)

        correlation_id = self.request_factory.new_correlation_id()
        orchestrations: tuple[OrchestrationResult, ...] = ()
        verified_resources = ()

        if resolution.decision.outcome == "information":
            executor = BoundTeamsConversationIntentExecutor(
                request_factory=self.request_factory,
                orchestrator=self.orchestrator,
                principal=principal,
                identity=request.identity,
                correlation_id=correlation_id,
            )
            read_result = self.progressive_reads.fulfill_result(
                question=request.text.strip(),
                resolution=resolution,
                executor=executor,
            )
            response_text = read_result.answer.text.strip()
            verified_resources = read_result.verified_resources
            orchestrations = tuple(executor.results)
            if not orchestrations:
                raise RuntimeError(
                    "information turn produced no Central Orchestrator evidence"
                )
        elif resolution.decision.outcome == "clarify":
            response_text = self.text_quality.finalize(
                human_text=request.text.strip(),
                kind="clarification",
                candidate=resolution.decision.clarification_question or "",
                internal_identifiers=self._internal_capability_identifiers(),
            )
        else:
            response_text = self.text_quality.finalize(
                human_text=request.text.strip(),
                kind="conversation",
                candidate=resolution.decision.conversational_response or "",
                internal_identifiers=self._internal_capability_identifiers(),
            )

        if not response_text:
            raise RuntimeError("Conversation Experience produced empty human-facing text")

        transport_message_id = self.transport.send(
            conversation_id=request.identity.conversation_id,
            text=response_text,
            correlation_id=correlation_id,
        )
        if not transport_message_id.strip():
            raise RuntimeError("Teams transport did not return a message identifier")

        # Advance durable entity context only after the human-facing response was
        # successfully delivered. Identity comes from provider-verified durable resource
        # resolution, never from parsing rendered prose or promoting a human selector.
        if verified_resources:
            resolved_context = resolution.context.with_verified_entities(
                tuple(item.entity for item in verified_resources),
                active_kinds={
                    item.active_kind: item.entity.ref
                    for item in verified_resources
                },
                resolutions=tuple(
                    item.resolution for item in verified_resources
                ),
            )
            self.context_store.put(resolved_context)

        return TeamsConversationExperienceResult(
            response_text=response_text,
            transport_message_id=transport_message_id.strip(),
            correlation_id=correlation_id,
            orchestrations=orchestrations,
        )

    def _load_or_create(
        self,
        *,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
    ) -> DynamicConversationContext:
        existing = self.context_store.get(
            organization_id=principal.organization_id,
            principal_id=principal.principal_id,
            conversation_id=identity.conversation_id,
        )
        if existing is not None:
            return existing
        return DynamicConversationContext(
            conversation_id=identity.conversation_id,
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
        )

    def _internal_capability_identifiers(self) -> tuple[str, ...]:
        return tuple(
            item.capability_name
            for item in self.experience.catalog.list_available()
        )
