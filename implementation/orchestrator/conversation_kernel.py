"""Model-independent conversation kernel contracts for Jason.

The kernel interprets human language into provider-independent information needs or
bounded conversational outcomes. It is intentionally blind to capability names,
providers, connectors, schemas, API operations, and execution handles. Those belong
behind the Central Orchestrator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence, TypeVar

from .dynamic_conversation_kernel import DynamicConversationContext


_MAX_TEXT_CHARS = 4000
_MAX_NEEDS = 12
_MAX_LABEL_CHARS = 512
_MAX_RESPONSE_CHARS = 2400
_ALLOWED_AUTHORITIES = {
    "observe",
    "recommend",
    "request_approval",
    "execute",
    "administer",
}
_ALLOWED_TEMPORAL_SCOPES = {
    "unspecified",
    "current",
    "most_recent",
    "historical",
}
_ALLOWED_COMPLETENESS = {"sufficient", "complete"}
_FORBIDDEN_INTERNAL_KEYS = {
    "provider",
    "provider_id",
    "connector",
    "connector_id",
    "capability",
    "capability_id",
    "capability_name",
    "operation",
    "api",
    "api_path",
    "endpoint",
    "shell",
    "shell_command",
    "agent",
    "agent_id",
    "target_agent",
}


class ConversationKernelError(ValueError):
    """A model proposal violated the bounded conversation contract."""


class StructuredConversationReasoner(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ReasoningBackend:
    """One replaceable reasoning backend ordered by expected cost."""

    name: str
    client: StructuredConversationReasoner
    max_attempts: int = 1

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("reasoning backend name is required")
        if self.max_attempts < 1 or self.max_attempts > 3:
            raise ValueError("reasoning backend attempts must be between 1 and 3")


@dataclass(frozen=True, slots=True)
class ReasoningAttempt:
    backend: str
    attempt: int
    outcome: str
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class ValidatedReasoningPool:
    """Try lower-cost backends first and expose only validated structured results.

    This is a logical part of the Conversation Kernel, not a separate authority or
    execution service. Raw model output never becomes a user-facing response here.
    """

    backends: tuple[ReasoningBackend, ...]

    def __post_init__(self) -> None:
        if not self.backends:
            raise ValueError("at least one reasoning backend is required")
        names = [item.name for item in self.backends]
        if len(names) != len(set(names)):
            raise ValueError("reasoning backend names must be unique")

    def complete_validated(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int,
        validator: Callable[[Mapping[str, Any]], T],
    ) -> tuple[T, tuple[ReasoningAttempt, ...]]:
        attempts: list[ReasoningAttempt] = []
        last_error: Exception | None = None
        for backend in self.backends:
            for attempt in range(1, backend.max_attempts + 1):
                try:
                    proposal = backend.client.complete(
                        system=system,
                        user=user,
                        schema=schema,
                        max_output_tokens=max_output_tokens,
                    )
                    validated = validator(proposal)
                except Exception as error:
                    last_error = error
                    attempts.append(
                        ReasoningAttempt(
                            backend=backend.name,
                            attempt=attempt,
                            outcome="rejected",
                            error_type=type(error).__name__,
                        )
                    )
                    continue
                attempts.append(
                    ReasoningAttempt(
                        backend=backend.name,
                        attempt=attempt,
                        outcome="accepted",
                    )
                )
                return validated, tuple(attempts)
        if last_error is None:
            raise ConversationKernelError("reasoning pool exhausted without a result")
        raise ConversationKernelError(
            "all configured reasoning backends failed bounded validation"
        ) from last_error


@dataclass(frozen=True, slots=True)
class InformationTarget:
    """A provider-independent target grounded in the current turn or verified context."""

    kind: str
    source: str
    reference: str
    entity_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.reference.strip():
            raise ConversationKernelError("information target kind and reference are required")
        if self.source not in {"literal", "verified_entity"}:
            raise ConversationKernelError("information target source is invalid")
        if self.source == "literal" and self.entity_ref is not None:
            raise ConversationKernelError("literal information target cannot carry entity_ref")
        if self.source == "verified_entity" and not (self.entity_ref or "").strip():
            raise ConversationKernelError("verified entity target requires entity_ref")


@dataclass(frozen=True, slots=True)
class InformationNeed:
    """What the human needs, without prescribing how Jason must obtain it."""

    target: InformationTarget
    need: str
    authority: str = "observe"
    temporal_scope: str = "unspecified"
    completeness: str = "sufficient"
    relationship: str | None = None

    def __post_init__(self) -> None:
        if not self.need.strip():
            raise ConversationKernelError("information need description is required")
        if self.authority not in _ALLOWED_AUTHORITIES:
            raise ConversationKernelError("information need authority is invalid")
        if self.temporal_scope not in _ALLOWED_TEMPORAL_SCOPES:
            raise ConversationKernelError("information need temporal scope is invalid")
        if self.completeness not in _ALLOWED_COMPLETENESS:
            raise ConversationKernelError("information need completeness is invalid")
        if self.relationship is not None and not self.relationship.strip():
            raise ConversationKernelError("information need relationship must be non-empty")


@dataclass(frozen=True, slots=True)
class ConversationKernelDecision:
    """A validated turn decision; never an execution plan or provider result."""

    outcome: str
    information_needs: tuple[InformationNeed, ...] = ()
    clarification_question: str | None = None
    conversational_response: str | None = None
    topic: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {"information", "clarify", "conversation"}:
            raise ConversationKernelError("conversation kernel outcome is invalid")
        if len(self.information_needs) > _MAX_NEEDS:
            raise ConversationKernelError("conversation kernel need count exceeds safety bound")
        if self.outcome == "information":
            if not self.information_needs:
                raise ConversationKernelError("information outcome requires at least one need")
            if self.clarification_question is not None or self.conversational_response is not None:
                raise ConversationKernelError("information outcome cannot carry human-facing text")
        elif self.information_needs:
            raise ConversationKernelError("non-information outcome cannot carry information needs")
        if self.outcome == "clarify":
            if not (self.clarification_question or "").strip():
                raise ConversationKernelError("clarify outcome requires a question")
            if self.conversational_response is not None:
                raise ConversationKernelError("clarify outcome cannot carry conversation response")
        elif self.clarification_question is not None:
            raise ConversationKernelError("only clarify outcome may carry a clarification question")
        if self.outcome == "conversation":
            if not (self.conversational_response or "").strip():
                raise ConversationKernelError("conversation outcome requires a candidate response")
        elif self.conversational_response is not None:
            raise ConversationKernelError("only conversation outcome may carry a candidate response")


_SYSTEM_INSTRUCTIONS = """You are Jason's Conversation Kernel. Interpret what the human means at the user-experience level. Do not select or name providers, connectors, capabilities, API operations, internal registries, shells, agents, or implementation paths. For information or action requests, describe only the provider-independent target, the information or outcome needed, requested authority, time scope, completeness, and any material relationship. A target may be grounded either in an exact literal from the current human message or in an entity already verified in supplied conversation context. Do not invent, normalize, expand, or transform identifiers. Ask for clarification only when choosing would materially change the target, authority, action, risk, or meaning. Uncertainty about where Jason should obtain evidence is never a reason to ask the human. Return the complete bounded set of information needs when the human asks for several things. Conversation-only text is a candidate response and must still pass Jason's downstream experience/quality controls before reaching a human. Return only the required structured object."""


@dataclass(frozen=True, slots=True)
class ConversationKernel:
    """Interpret one authenticated conversation turn without seeing capabilities."""

    reasoning: ValidatedReasoningPool

    def interpret(
        self,
        *,
        text: str,
        context: DynamicConversationContext,
    ) -> tuple[ConversationKernelDecision, tuple[ReasoningAttempt, ...]]:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("conversation text is required")
        if len(clean_text) > _MAX_TEXT_CHARS:
            raise ValueError("conversation text exceeds safety bound")

        known_refs = tuple(entity.ref for entity in context.entities)
        payload = {
            "message": clean_text,
            "context": {
                "conversation_id": context.conversation_id,
                "organization_id": context.organization_id,
                "active_topic": context.active_topic,
                "active_entity_refs": dict(context.active_entity_refs),
                "entities": [
                    {
                        "ref": item.ref,
                        "kind": item.kind,
                        "canonical_id": item.canonical_id,
                        "display_name": item.display_name,
                        "provenance": item.provenance,
                    }
                    for item in context.entities
                ],
                "recent_resolutions": [
                    {
                        "mention": item.mention,
                        "entity_ref": item.entity_ref,
                        "basis": item.basis,
                    }
                    for item in context.recent_resolutions
                ],
            },
        }
        return self.reasoning.complete_validated(
            system=_SYSTEM_INSTRUCTIONS,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=_decision_schema(known_refs),
            max_output_tokens=768,
            validator=lambda proposal: _validate_decision(
                proposal=proposal,
                text=clean_text,
                context=context,
            ),
        )


def _decision_schema(known_refs: tuple[str, ...]) -> Mapping[str, Any]:
    entity_ref_schema: dict[str, Any] = {"type": ["string", "null"]}
    if known_refs:
        entity_ref_schema["enum"] = [*known_refs, None]
    else:
        entity_ref_schema["enum"] = [None]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "outcome",
            "information_needs",
            "clarification_question",
            "conversational_response",
            "topic",
        ],
        "properties": {
            "outcome": {
                "type": "string",
                "enum": ["information", "clarify", "conversation"],
            },
            "information_needs": {
                "type": "array",
                "maxItems": _MAX_NEEDS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "target_kind",
                        "target_source",
                        "target_reference",
                        "target_entity_ref",
                        "need",
                        "authority",
                        "temporal_scope",
                        "completeness",
                        "relationship",
                    ],
                    "properties": {
                        "target_kind": {"type": "string", "maxLength": _MAX_LABEL_CHARS},
                        "target_source": {
                            "type": "string",
                            "enum": ["literal", "verified_entity"],
                        },
                        "target_reference": {
                            "type": "string",
                            "maxLength": _MAX_LABEL_CHARS,
                        },
                        "target_entity_ref": entity_ref_schema,
                        "need": {"type": "string", "maxLength": _MAX_LABEL_CHARS},
                        "authority": {
                            "type": "string",
                            "enum": sorted(_ALLOWED_AUTHORITIES),
                        },
                        "temporal_scope": {
                            "type": "string",
                            "enum": sorted(_ALLOWED_TEMPORAL_SCOPES),
                        },
                        "completeness": {
                            "type": "string",
                            "enum": sorted(_ALLOWED_COMPLETENESS),
                        },
                        "relationship": {
                            "type": ["string", "null"],
                            "maxLength": _MAX_LABEL_CHARS,
                        },
                    },
                },
            },
            "clarification_question": {
                "type": ["string", "null"],
                "maxLength": _MAX_RESPONSE_CHARS,
            },
            "conversational_response": {
                "type": ["string", "null"],
                "maxLength": _MAX_RESPONSE_CHARS,
            },
            "topic": {
                "type": ["string", "null"],
                "maxLength": _MAX_LABEL_CHARS,
            },
        },
    }


def _validate_decision(
    *,
    proposal: Mapping[str, Any],
    text: str,
    context: DynamicConversationContext,
) -> ConversationKernelDecision:
    if not isinstance(proposal, Mapping):
        raise ConversationKernelError("conversation kernel proposal must be an object")
    forbidden = sorted(_FORBIDDEN_INTERNAL_KEYS.intersection(str(key) for key in proposal))
    if forbidden:
        raise ConversationKernelError("conversation kernel attempted internal execution selection")

    outcome = str(proposal.get("outcome", "")).strip().casefold()
    raw_needs = proposal.get("information_needs", ())
    if not isinstance(raw_needs, Sequence) or isinstance(raw_needs, (str, bytes)):
        raise ConversationKernelError("information_needs must be an array")
    if len(raw_needs) > _MAX_NEEDS:
        raise ConversationKernelError("information_needs exceeds safety bound")

    known = {entity.ref: entity for entity in context.entities}
    needs: list[InformationNeed] = []
    for raw in raw_needs:
        if not isinstance(raw, Mapping):
            raise ConversationKernelError("information need must be an object")
        forbidden = sorted(_FORBIDDEN_INTERNAL_KEYS.intersection(str(key) for key in raw))
        if forbidden:
            raise ConversationKernelError("information need attempted internal execution selection")

        kind = str(raw.get("target_kind", "")).strip()
        source = str(raw.get("target_source", "")).strip().casefold()
        reference = str(raw.get("target_reference", "")).strip()
        raw_entity_ref = raw.get("target_entity_ref")
        entity_ref = None if raw_entity_ref is None else str(raw_entity_ref).strip() or None
        if source == "literal":
            if entity_ref is not None:
                raise ConversationKernelError("literal target cannot carry target_entity_ref")
            if not reference or reference not in text:
                raise ConversationKernelError(
                    "literal target reference must be copied exactly from the human message"
                )
        elif source == "verified_entity":
            if entity_ref not in known:
                raise ConversationKernelError(
                    "target_entity_ref is not a verified context entity"
                )
            entity = known[entity_ref]
            if kind != entity.kind:
                raise ConversationKernelError(
                    "verified entity target kind must match verified entity data"
                )
            if reference not in {
                entity.canonical_id,
                entity.display_name,
            }:
                raise ConversationKernelError(
                    "verified entity target reference must use verified entity data"
                )

            # A model may refer to an already verified entity by either its
            # human-facing display name or its canonical identifier. Once the
            # entity_ref has been deterministically validated, however, the
            # execution-facing target is always bound locally to the durable
            # canonical identifier. Model output is never authoritative for
            # canonical resource identity.
            reference = entity.canonical_id
        else:
            raise ConversationKernelError("information target source is invalid")

        target = InformationTarget(
            kind=kind,
            source=source,
            reference=reference,
            entity_ref=entity_ref,
        )
        needs.append(
            InformationNeed(
                target=target,
                need=str(raw.get("need", "")).strip(),
                authority=str(raw.get("authority", "")).strip().casefold(),
                temporal_scope=str(raw.get("temporal_scope", "")).strip().casefold(),
                completeness=str(raw.get("completeness", "")).strip().casefold(),
                relationship=(
                    None
                    if raw.get("relationship") is None
                    else str(raw.get("relationship", "")).strip() or None
                ),
            )
        )

    clarification = proposal.get("clarification_question")
    clarification_text = (
        None if clarification is None else str(clarification).strip() or None
    )
    response = proposal.get("conversational_response")
    response_text = None if response is None else str(response).strip() or None
    topic = proposal.get("topic")
    topic_text = None if topic is None else str(topic).strip() or None

    return ConversationKernelDecision(
        outcome=outcome,
        information_needs=tuple(needs),
        clarification_question=clarification_text,
        conversational_response=response_text,
        topic=topic_text,
    )