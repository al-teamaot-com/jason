"""Governed conversational ingress for Microsoft Teams via OpenClaw.

OpenClaw is an authenticated transport/interface provider only. This module accepts
transport evidence, re-binds the Microsoft identity to Jason identity/organization,
resolves provider-neutral user intent into named Jason capabilities, and hands every
request to the Central Orchestrator. It never invokes a provider, shell command,
node, tool, or agent directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .contracts import OrchestrationRequest, OrchestrationResult
from .service import CentralOrchestrator
from .teams_conversation_continuation import ConversationContinuationState


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


class ConversationGuidanceRequiredError(ConversationIntentUnresolvedError):
    """A safe conversational answer is available without provider execution.

    This is used only for bounded guidance such as explaining prior Jason output or
    telling a human that a recognized semantic fact has no governed retrieval
    capability. It does not authorize or perform provider work.
    """

    def __init__(
        self,
        *,
        reason_code: str,
        guidance_text: str,
        requested_facts: tuple[str, ...] = (),
    ) -> None:
        reason_code = str(reason_code).strip()
        guidance_text = str(guidance_text).strip()
        facts = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in requested_facts
                if str(item).strip()
            )
        )
        if not reason_code or not guidance_text:
            raise ValueError("conversation guidance requires reason_code and text")
        if len(guidance_text) > 1600:
            raise ValueError("conversation guidance exceeds safety bound")
        self.reason_code = reason_code
        self.guidance_text = guidance_text
        self.requested_facts = facts
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


@dataclass(frozen=True, slots=True)
class ConversationRenderDecision:
    """User-facing text plus a bounded evidence-fulfillment decision.

    ``satisfies_request`` means the renderer established that the current governed
    result fully answers the bounded request represented by the intent. It is not a
    provider-routing or semantic-mapping decision.
    """

    text: str
    satisfies_request: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("conversation render decision text is required")


class TeamsConversationIdentityBinder(Protocol):
    def bind(self, evidence: TeamsConversationPrincipalEvidence) -> BoundConversationPrincipal | None: ...


class ConversationIntentResolver(Protocol):
    def resolve(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
    ) -> ConversationIntent | ConversationIntentPlan | None: ...


class ConversationContinuationStore(Protocol):
    def get(
        self,
        *,
        organization_id: str,
        principal_id: str,
        conversation_id: str,
    ) -> ConversationContinuationState | None: ...

    def put(
        self,
        *,
        principal_id: str,
        organization_id: str,
        conversation_id: str,
        last_message_id: str,
        response_kind: str,
        last_response_text: str,
        last_capability_name: str | None,
        requested_facts: tuple[str, ...],
        resource_selector: Mapping[str, str],
    ) -> ConversationContinuationState: ...


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
    continuation_store: ConversationContinuationStore | None = None

    def handle(self, request: TeamsConversationRequest) -> TeamsConversationFlowResult:
        principal = self.identity_binder.bind(request.identity)
        if principal is None:
            raise PermissionError("Teams identity is not bound to a governed Jason principal")

        continuation = self._load_continuation(
            principal=principal,
            identity=request.identity,
        )
        if continuation is not None and _is_reference_explanation(request.text):
            raise ConversationGuidanceRequiredError(
                reason_code="conversation_reference_explained",
                guidance_text=_reference_explanation(continuation),
                requested_facts=continuation.requested_facts,
            )

        try:
            resolved = self.intent_resolver.resolve(text=request.text.strip(), principal=principal)
        except ConversationGuidanceRequiredError as error:
            self._record_guidance(
                principal=principal,
                identity=request.identity,
                guidance=error,
                previous=continuation,
            )
            raise

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

        # Read plans acquire evidence progressively. Each step still crosses the
        # Central Orchestrator independently, but later steps are not invoked once a
        # renderer has established that the current governed evidence fully satisfies
        # the bounded request. Renderers without a fulfillment-decision surface retain
        # the legacy execute-all behavior.
        results: list[OrchestrationResult] = []
        executed_intents: list[ConversationIntent] = []
        rendered_parts: list[str] = []
        progressive = len(intents) > 1
        for orchestration_request, intent in zip(
            orchestration_requests,
            intents,
            strict=True,
        ):
            result = self.orchestrator.execute(orchestration_request)
            decision = self._render_decision(result=result, intent=intent)
            results.append(result)
            executed_intents.append(intent)
            rendered_parts.append(decision.text.strip())
            if progressive and decision.satisfies_request:
                rendered_parts = [decision.text.strip()]
                break

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

        self._record_result(
            principal=principal,
            identity=request.identity,
            intents=tuple(executed_intents),
            response_text=response_text,
        )

        return TeamsConversationFlowResult(
            orchestration=results[0],
            orchestrations=tuple(results),
            transport_message_id=transport_message_id.strip(),
        )

    def _render_decision(
        self,
        *,
        result: OrchestrationResult,
        intent: ConversationIntent,
    ) -> ConversationRenderDecision:
        decision_renderer = getattr(self.response_renderer, "render_decision", None)
        if callable(decision_renderer):
            decision = decision_renderer(result, intent)
            if not isinstance(decision, ConversationRenderDecision):
                raise TypeError("response render_decision returned an invalid decision")
            return decision
        return ConversationRenderDecision(
            text=self.response_renderer.render(result, intent),
            satisfies_request=False,
        )

    def _load_continuation(
        self,
        *,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
    ) -> ConversationContinuationState | None:
        if self.continuation_store is None:
            return None
        return self.continuation_store.get(
            organization_id=principal.organization_id,
            principal_id=principal.principal_id,
            conversation_id=identity.conversation_id,
        )

    def _record_guidance(
        self,
        *,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
        guidance: ConversationGuidanceRequiredError,
        previous: ConversationContinuationState | None,
    ) -> None:
        if self.continuation_store is None:
            return
        self.continuation_store.put(
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
            conversation_id=identity.conversation_id,
            last_message_id=identity.message_id,
            response_kind="guidance",
            last_response_text=guidance.guidance_text,
            last_capability_name=(
                None if previous is None else previous.last_capability_name
            ),
            requested_facts=(
                guidance.requested_facts
                or (() if previous is None else previous.requested_facts)
            ),
            resource_selector=(
                {} if previous is None else previous.resource_selector
            ),
        )

    def _record_result(
        self,
        *,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
        intents: tuple[ConversationIntent, ...],
        response_text: str,
    ) -> None:
        if self.continuation_store is None:
            return

        facts: list[str] = []
        selector: dict[str, str] = {}
        excluded_argument_keys = {
            "requested_facts",
            "evidence_contexts",
            "result_intent",
            "completeness_requirement",
            "relationship_type",
            "temporal_semantics",
        }
        for intent in intents:
            raw_facts = intent.arguments.get("requested_facts", ())
            if isinstance(raw_facts, (list, tuple)):
                for fact in raw_facts:
                    normalized = str(fact).strip()
                    if normalized and normalized not in facts:
                        facts.append(normalized)
            for key, value in intent.arguments.items():
                if key in excluded_argument_keys or not isinstance(value, str):
                    continue
                clean_key = str(key).strip()
                clean_value = value.strip()
                if clean_key and clean_value:
                    selector.setdefault(clean_key, clean_value)

        self.continuation_store.put(
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
            conversation_id=identity.conversation_id,
            last_message_id=identity.message_id,
            response_kind="result",
            last_response_text=response_text,
            last_capability_name=(
                intents[0].capability_name if len(intents) == 1 else "conversation.plan"
            ),
            requested_facts=tuple(facts),
            resource_selector=selector,
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


def _normalized_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def _is_reference_explanation(text: str) -> bool:
    """Recognize grammar-level deictic explanation requests, not sentence variants."""

    words = _normalized_words(text)
    reference_words = {"that", "this", "it", "those", "these", "them"}
    explanation_words = {"mean", "means", "explain", "clarify", "understand"}
    return bool(words.intersection(reference_words)) and bool(
        words.intersection(explanation_words)
    )


def _reference_explanation(state: ConversationContinuationState) -> str:
    topic = ", ".join(state.requested_facts) or "the previous Jason result"
    if state.response_kind == "guidance":
        return f"That refers to my previous guidance about {topic}. {state.last_response_text}"
    return f"That refers to my previous result about {topic}: {state.last_response_text}"
