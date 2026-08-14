"""Governed conversational ingress for Microsoft Teams via OpenClaw.

OpenClaw is an authenticated transport/interface provider only. This module accepts
transport evidence, re-binds the Microsoft identity to Jason identity/organization,
resolves provider-neutral user intent into named Jason capabilities, and hands every
request to the Central Orchestrator. It never invokes a provider, shell command,
node, tool, or agent directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .contracts import OrchestrationRequest, OrchestrationResult
from .service import CentralOrchestrator


class ConversationIntentUnresolvedError(LookupError):
    """The human turn could not be mapped to a governed Jason capability intent."""


class ConversationClarificationRequiredError(
    ConversationIntentUnresolvedError
):
    """The human must disambiguate bounded governed facts before execution."""

    def __init__(
        self,
        *,
        reason_code: str,
        candidate_facts: tuple[str, ...],
    ) -> None:
        reason_code = str(reason_code).strip()

        if not reason_code:
            raise ValueError(
                "clarification reason_code is required"
            )

        normalized: list[str] = []

        for raw_fact in candidate_facts:
            fact = str(raw_fact).strip()

            if fact and fact not in normalized:
                normalized.append(fact)

        if len(normalized) < 2:
            raise ValueError(
                "clarification requires at least two "
                "distinct governed candidate facts"
            )

        self.reason_code = reason_code
        self.candidate_facts = tuple(normalized)

        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class TeamsConversationPrincipalEvidence:
    """Authenticated transport identity evidence supplied by the Teams boundary."""

    microsoft_tenant_id: str
    microsoft_object_id: str
    authentication_assurance: str
    conversation_id: str
    message_id: str

    def __post_init__(self) -> None:
        values = {
            "microsoft_tenant_id": self.microsoft_tenant_id,
            "microsoft_object_id": self.microsoft_object_id,
            "authentication_assurance": self.authentication_assurance,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
        }
        missing = sorted(name for name, value in values.items() if not value.strip())
        if missing:
            raise ValueError("Teams identity evidence fields are empty: " + ", ".join(missing))


@dataclass(frozen=True, slots=True)
class BoundConversationPrincipal:
    """Jason-owned identity and tenant binding derived from transport evidence."""

    principal_id: str
    organization_id: str
    client_id: str | None = None
    email_address: str | None = None

    def __post_init__(self) -> None:
        if not self.principal_id.strip() or not self.organization_id.strip():
            raise ValueError("bound Jason principal and organization are required")
        if self.client_id is not None and not self.client_id.strip():
            raise ValueError("client_id must be non-empty when supplied")
        if self.email_address is not None:
            email = self.email_address.strip()
            if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
                raise ValueError("email_address must be valid when supplied")


@dataclass(frozen=True, slots=True)
class ConversationIntent:
    """Provider-neutral governed capability request derived from human language.

    execution_mode describes how Jason may satisfy the capability (for example,
    deterministic provider execution). permission_mode describes what authority the
    human is requesting (for example, observe). Keeping them separate prevents a
    read-only authority request from being confused with execution-provider policy.
    """

    capability_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    capability_version: str | None = None
    execution_mode: str = "deterministic"
    permission_mode: str = "observe"
    risk: str = "low"

    def __post_init__(self) -> None:
        if not self.capability_name.strip():
            raise ValueError("conversation intent capability_name is required")
        if not self.execution_mode.strip() or not self.permission_mode.strip() or not self.risk.strip():
            raise ValueError("conversation intent execution mode, permission mode, and risk are required")
        if self.permission_mode not in {
            "observe",
            "recommend",
            "request_approval",
            "execute",
            "administer",
        }:
            raise ValueError("conversation intent permission_mode is invalid")
        forbidden = {"target_agent", "agent_endpoint", "invoke_agent", "recipient_agent"}
        present = sorted(forbidden.intersection(self.arguments))
        if present:
            raise ValueError(
                "direct agent invocation is prohibited; request a named capability instead: "
                + ", ".join(present)
            )


@dataclass(frozen=True, slots=True)
class ConversationIntentPlan:
    """A bounded set of independent governed read intents for one human turn.

    Multi-step conversation plans are intentionally limited to observe-only requests.
    Each step is still separately resolved, authorized, provider-selected, invoked,
    evidenced, and audited by the Central Orchestrator. This does not create a path
    for batching mutations or bypassing normal capability governance.
    """

    intents: tuple[ConversationIntent, ...]

    def __post_init__(self) -> None:
        if len(self.intents) < 2:
            raise ValueError("conversation intent plan requires at least two intents")
        if len(self.intents) > 20:
            raise ValueError("conversation intent plan exceeds the 20-step safety bound")
        if any(intent.permission_mode != "observe" for intent in self.intents):
            raise PermissionError("multi-step conversation plans are read-only")
        modes = {intent.execution_mode for intent in self.intents}
        if len(modes) != 1:
            raise ValueError("multi-step conversation intents must use one execution mode")


@dataclass(frozen=True, slots=True)
class TeamsConversationRequest:
    text: str
    identity: TeamsConversationPrincipalEvidence

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Teams conversation text is required")


class TeamsConversationIdentityBinder(Protocol):
    def bind(self, evidence: TeamsConversationPrincipalEvidence) -> BoundConversationPrincipal | None: ...


class ConversationIntentResolver(Protocol):
    def resolve(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ConversationIntent | ConversationIntentPlan | None: ...


class ConversationOrchestrationRequestFactory(Protocol):
    """Build governed requests within one conversation correlation scope."""

    def new_correlation_id(self) -> str: ...

    def build(
        self,
        *,
        principal: BoundConversationPrincipal,
        intent: ConversationIntent,
        identity: TeamsConversationPrincipalEvidence,
        correlation_id: str,
    ) -> OrchestrationRequest: ...


class TeamsConversationResponseRenderer(Protocol):
    def render(self, result: OrchestrationResult, intent: ConversationIntent) -> str: ...


class TeamsConversationTransport(Protocol):
    def send(
        self,
        *,
        conversation_id: str,
        text: str,
        correlation_id: str,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class TeamsConversationFlowResult:
    orchestration: OrchestrationResult
    transport_message_id: str
    orchestrations: tuple[OrchestrationResult, ...] = ()

    def __post_init__(self) -> None:
        if not self.orchestrations:
            object.__setattr__(self, "orchestrations", (self.orchestration,))
        elif self.orchestrations[0] is not self.orchestration:
            raise ValueError("primary orchestration must be the first orchestration result")


@dataclass(frozen=True, slots=True)
class TeamsConversationFlow:
    """Route one authenticated Teams turn through Jason governance and orchestration."""

    identity_binder: TeamsConversationIdentityBinder
    intent_resolver: ConversationIntentResolver
    request_factory: ConversationOrchestrationRequestFactory
    orchestrator: CentralOrchestrator
    response_renderer: TeamsConversationResponseRenderer
    transport: TeamsConversationTransport

    def handle(self, request: TeamsConversationRequest) -> TeamsConversationFlowResult:
        principal = self.identity_binder.bind(request.identity)
        if principal is None:
            raise PermissionError("Teams identity is not bound to a governed Jason principal")

        resolved = self.intent_resolver.resolve(text=request.text.strip(), principal=principal)
        if resolved is None:
            raise ConversationIntentUnresolvedError(
                "no governed Jason capability intent could be resolved"
            )

        intents = (
            resolved.intents
            if isinstance(resolved, ConversationIntentPlan)
            else (resolved,)
        )

        correlation_id = self.request_factory.new_correlation_id()

        orchestration_requests: list[OrchestrationRequest] = []
        for intent in intents:
            orchestration_request = self.request_factory.build(
                principal=principal,
                intent=intent,
                identity=request.identity,
                correlation_id=correlation_id,
            )
            self._validate_bound_request(
                orchestration_request=orchestration_request,
                principal=principal,
                intent=intent,
            )
            orchestration_requests.append(orchestration_request)

        if any(
            item.correlation_id != correlation_id
            for item in orchestration_requests
        ):
            raise PermissionError(
                "conversation requests must retain the turn correlation identity"
            )

        # Every step crosses the Central Orchestrator independently. A failed or
        # unavailable read does not suppress independent successful facts; the
        # response renderer preserves each step's provider provenance and status.
        results = tuple(
            self.orchestrator.execute(orchestration_request)
            for orchestration_request in orchestration_requests
        )

        rendered_parts = tuple(
            self.response_renderer.render(result, intent).strip()
            for result, intent in zip(results, intents, strict=True)
        )
        if not rendered_parts or any(not part for part in rendered_parts):
            raise RuntimeError("conversation response renderer returned empty text")
        response_text = "\n".join(rendered_parts)

        transport_message_id = self.transport.send(
            conversation_id=request.identity.conversation_id,
            text=response_text,
            correlation_id=correlation_id,
        )
        if not transport_message_id.strip():
            raise RuntimeError("Teams transport did not return a message identifier")

        return TeamsConversationFlowResult(
            orchestration=results[0],
            orchestrations=results,
            transport_message_id=transport_message_id.strip(),
        )

    @staticmethod
    def _validate_bound_request(
        *,
        orchestration_request: OrchestrationRequest,
        principal: BoundConversationPrincipal,
        intent: ConversationIntent,
    ) -> None:
        if orchestration_request.principal_id != principal.principal_id:
            raise PermissionError("orchestration request principal does not match bound Teams identity")
        if orchestration_request.organization_id != principal.organization_id:
            raise PermissionError("orchestration request organization does not match bound Teams identity")
        if orchestration_request.client_id != principal.client_id:
            raise PermissionError("orchestration request client does not match bound Teams identity")
        if orchestration_request.capability_name != intent.capability_name:
            raise PermissionError("request factory changed the governed capability intent")
        if orchestration_request.requested_mode != intent.execution_mode:
            raise PermissionError("request factory changed the governed execution mode")
        if orchestration_request.permission_mode != intent.permission_mode:
            raise PermissionError("request factory changed the governed permission mode")
        if orchestration_request.requester_kind != "human":
            raise PermissionError("Teams conversational requests must retain human requester identity")
