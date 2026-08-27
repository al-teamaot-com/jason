"""Provider-independent conversational context and dynamic capability resolution.

This module deliberately contains no question-to-field, phrase-to-provider, synonym,
or provider-specific semantic mappings.  Human language is interpreted against the
current governed conversation context and the capabilities actually offered to the
resolver at runtime.  Deterministic code validates every model-selected capability
and contextual reference before orchestration may use the plan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


_MAX_ENTITIES = 32
_MAX_RESOLUTIONS = 32
_MAX_CAPABILITIES = 256
_MAX_REQUIREMENTS = 12
_MAX_TEXT_CHARS = 4000
_MAX_LABEL_CHARS = 256

# Dynamic planning is control-plane reasoning only. The model identifies bounded
# requirements and references; it does not generate evidence, explanations, or the
# final human response. Keep its generation allowance deliberately small enough that
# a low-cost backend cannot monopolize the synchronous conversation boundary.
_DYNAMIC_PLAN_OUTPUT_TOKENS = 160


class DynamicConversationPlanError(ValueError):
    """A model proposal violated the bounded dynamic conversation contract."""


class StructuredConversationClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        schema: Mapping[str, Any],
        max_output_tokens: int = 160,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ConversationEntity:
    """A provider-independent entity already established by governed evidence."""

    ref: str
    kind: str
    canonical_id: str
    display_name: str
    provenance: str

    def __post_init__(self) -> None:
        values = (self.ref, self.kind, self.canonical_id, self.display_name, self.provenance)
        if any(not str(value).strip() for value in values):
            raise ValueError("conversation entity fields must be non-empty")
        if len(self.display_name) > _MAX_LABEL_CHARS:
            raise ValueError("conversation entity display name exceeds safety bound")


@dataclass(frozen=True, slots=True)
class ConversationReferenceResolution:
    """Auditable resolution of human reference text to an established entity."""

    mention: str
    entity_ref: str
    basis: str

    def __post_init__(self) -> None:
        if not self.mention.strip() or not self.entity_ref.strip() or not self.basis.strip():
            raise ValueError("conversation reference resolution fields must be non-empty")
        if len(self.mention) > _MAX_LABEL_CHARS or len(self.basis) > _MAX_LABEL_CHARS:
            raise ValueError("conversation reference resolution exceeds safety bound")


@dataclass(frozen=True, slots=True)
class DynamicConversationContext:
    """Small, bounded, provider-independent state for one authenticated conversation."""

    conversation_id: str
    principal_id: str
    organization_id: str
    entities: tuple[ConversationEntity, ...] = ()
    active_entity_refs: Mapping[str, str] = field(default_factory=dict)
    active_topic: str | None = None
    recent_resolutions: tuple[ConversationReferenceResolution, ...] = ()

    def __post_init__(self) -> None:
        if not self.conversation_id.strip() or not self.principal_id.strip() or not self.organization_id.strip():
            raise ValueError("conversation, principal, and organization are required")
        if len(self.entities) > _MAX_ENTITIES:
            raise ValueError("conversation entity set exceeds safety bound")
        if len(self.recent_resolutions) > _MAX_RESOLUTIONS:
            raise ValueError("conversation resolution history exceeds safety bound")
        refs = [entity.ref for entity in self.entities]
        if len(refs) != len(set(refs)):
            raise ValueError("conversation entity refs must be unique")
        known = set(refs)
        for kind, ref in self.active_entity_refs.items():
            if not str(kind).strip() or not str(ref).strip():
                raise ValueError("active entity references must be non-empty")
            if ref not in known:
                raise ValueError("active entity reference must name an established entity")
        for item in self.recent_resolutions:
            if item.entity_ref not in known:
                raise ValueError("reference resolution must name an established entity")
        if self.active_topic is not None and len(self.active_topic.strip()) > _MAX_LABEL_CHARS:
            raise ValueError("active conversation topic exceeds safety bound")

    def entity(self, ref: str) -> ConversationEntity:
        for entity in self.entities:
            if entity.ref == ref:
                return entity
        raise KeyError(ref)

    def with_verified_entities(
        self,
        entities: Sequence[ConversationEntity],
        *,
        active_kinds: Mapping[str, str] | None = None,
        topic: str | None = None,
        resolutions: Sequence[ConversationReferenceResolution] = (),
    ) -> "DynamicConversationContext":
        """Merge only caller-supplied *verified* entities into bounded conversation state.

        The model cannot call this method directly.  The caller is responsible for
        creating ConversationEntity records only after normal provider/evidence
        verification.  Existing refs are replaced by newer verified records.
        """

        by_ref = {item.ref: item for item in self.entities}
        for item in entities:
            by_ref[item.ref] = item
        merged_entities = tuple(by_ref.values())[-_MAX_ENTITIES:]
        known = {item.ref for item in merged_entities}

        active = {
            str(kind): str(ref)
            for kind, ref in self.active_entity_refs.items()
            if ref in known
        }
        for kind, ref in (active_kinds or {}).items():
            if ref not in known:
                raise ValueError("new active entity reference must be verified")
            active[str(kind)] = str(ref)

        history = tuple(self.recent_resolutions) + tuple(resolutions)
        history = tuple(item for item in history if item.entity_ref in known)[-_MAX_RESOLUTIONS:]

        return DynamicConversationContext(
            conversation_id=self.conversation_id,
            principal_id=self.principal_id,
            organization_id=self.organization_id,
            entities=merged_entities,
            active_entity_refs=active,
            active_topic=self.active_topic if topic is None else topic.strip() or None,
            recent_resolutions=history,
        )


@dataclass(frozen=True, slots=True)
class OfferedConversationCapability:
    """Self-describing capability offered by the governed runtime for this turn."""

    capability_id: str
    description: str
    provider: str | None = None
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    permission_mode: str = "observe"
    risk: str = "low"

    def __post_init__(self) -> None:
        if not self.capability_id.strip() or not self.description.strip():
            raise ValueError("offered capability id and description are required")
        if self.provider is not None and not self.provider.strip():
            raise ValueError("provider must be non-empty when supplied")
        if self.permission_mode not in {
            "observe", "recommend", "request_approval", "execute", "administer"
        }:
            raise ValueError("offered capability permission mode is invalid")
        if not self.risk.strip():
            raise ValueError("offered capability risk is required")

    def model_view(self) -> Mapping[str, Any]:
        return {
            "capability_id": self.capability_id,
            "description": self.description,
            "provider": self.provider,
            "input_schema": dict(self.input_schema),
            "output_schema": dict(self.output_schema),
            "permission_mode": self.permission_mode,
            "risk": self.risk,
        }

    def discovery_view(self) -> Mapping[str, Any]:
        """Return only metadata needed to choose a governed capability.

        Discovery determines *what* governed operation can satisfy the human
        request. Selector choice and literal grounding are downstream binding
        responsibilities. Provider identity, schemas, and selector names are
        therefore intentionally excluded from the planner-facing projection.
        """
        return {
            "capability_id": self.capability_id,
            "description": self.description,
            "permission_mode": self.permission_mode,
            "risk": self.risk,
        }


@dataclass(frozen=True, slots=True)
class DynamicCapabilityRequirement:
    capability_id: str
    purpose: str
    entity_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.capability_id.strip() or not self.purpose.strip():
            raise ValueError("dynamic capability requirement fields must be non-empty")
        if len(self.entity_refs) > _MAX_ENTITIES:
            raise ValueError("dynamic capability requirement references too many entities")


@dataclass(frozen=True, slots=True)
class DynamicConversationPlan:
    """A validated conversational decision; never provider evidence itself."""

    outcome: str
    requirements: tuple[DynamicCapabilityRequirement, ...] = ()
    resolved_references: tuple[ConversationReferenceResolution, ...] = ()
    topic: str | None = None
    clarification_question: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {"plan", "clarify", "conversation"}:
            raise DynamicConversationPlanError("dynamic conversation outcome is invalid")
        if len(self.requirements) > _MAX_REQUIREMENTS:
            raise DynamicConversationPlanError("dynamic capability plan exceeds safety bound")
        if self.outcome == "plan" and not self.requirements:
            raise DynamicConversationPlanError("plan outcome requires at least one capability")
        if self.outcome != "plan" and self.requirements:
            raise DynamicConversationPlanError("non-plan outcome cannot execute capabilities")
        if self.outcome == "clarify":
            if not self.clarification_question or not self.clarification_question.strip():
                raise DynamicConversationPlanError("clarify outcome requires a question")
        elif self.clarification_question is not None:
            raise DynamicConversationPlanError("only clarify outcome may carry a clarification question")


@dataclass(frozen=True, slots=True)
class DynamicConversationResolver:
    """Resolve language from runtime context + runtime capabilities, with no static maps."""

    client: StructuredConversationClient

    def resolve(
        self,
        *,
        text: str,
        context: DynamicConversationContext,
        capabilities: Sequence[OfferedConversationCapability],
    ) -> DynamicConversationPlan:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("conversation text is required")
        if len(clean_text) > _MAX_TEXT_CHARS:
            raise ValueError("conversation text exceeds safety bound")
        offered = tuple(capabilities)
        if not offered:
            raise ValueError("at least one governed capability must be offered")
        if len(offered) > _MAX_CAPABILITIES:
            raise ValueError("offered capability catalog exceeds safety bound")
        ids = [item.capability_id for item in offered]
        if len(ids) != len(set(ids)):
            raise ValueError("offered capability ids must be unique")

        known_refs = tuple(entity.ref for entity in context.entities)
        schema = _plan_schema(tuple(ids), known_refs)
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
            "capabilities": [item.discovery_view() for item in offered],
        }
        proposal = self.client.complete(
            system=_SYSTEM_INSTRUCTIONS,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=schema,
            max_output_tokens=_DYNAMIC_PLAN_OUTPUT_TOKENS,
        )
        return _validate_plan(proposal, offered_ids=set(ids), known_refs=set(known_refs))


_SYSTEM_INSTRUCTIONS = """You are Jason's bounded conversational planner. Interpret the human message using only the supplied conversation context and the self-describing governed capabilities supplied for this turn. There are no hidden phrase-to-provider, synonym, question-to-field, or fact mappings. Resolve references such as pronouns only when the supplied context supports the resolution. Select capabilities by their runtime discovery descriptions, not by hard-coded provider assumptions. Selector selection and argument grounding happen after planning and are not human-facing choices. Never ask the human whether an explicitly supplied target literal should be treated as one internal selector field or another. If the human has clearly identified the target and an offered governed read or search capability can inspect that kind of resource, plan the capability and let the downstream grounding stage bind the exact human-supplied literal. A capability selection is only a request to the Central Orchestrator; it does not grant authority and does not supply factual evidence. Never invent operational facts, entity identifiers, capabilities, or provider results. Names or identifiers explicitly present in the current human message do not require a pre-existing conversation entity. entity_refs and resolved_references are only for references to entities already established in the supplied conversation context. When the target is explicitly named in the current message, select the appropriate governed discovery/read capability without inventing a context entity; the bounded grounding stage can bind the exact human-supplied literal. Do not ask the human to choose or provide an internal provider, registry, log, evidence source, or evidence location when an offered governed read/search capability can inspect the clearly identified resource. Uncertainty about whether a requested fact exists in returned evidence is not material ambiguity. For a clear factual read, select the best matching provider-neutral read/search capability using its resource types, business purpose, operation, and selectors, then let downstream governed evidence interpretation determine whether the requested fact is actually supported. Do not substitute a more specialized evidence collection merely because it might contain the fact when a general resource read better matches the human's target. If choosing among plausible meanings would materially change the target, authority, requested action, risk, or meaning, return clarify with one concise natural clarification question. Otherwise return the complete bounded plan needed for the user's request. Use conversation only when no capability invocation is required. Return only the structured object required by the schema."""


def _plan_schema(
    capability_ids: tuple[str, ...],
    entity_refs: tuple[str, ...],
) -> Mapping[str, Any]:
    has_context_entities = bool(entity_refs)

    entity_ref_schema: dict[str, Any] = {
        "type": "string",
    }

    if has_context_entities:
        entity_ref_schema["enum"] = list(entity_refs)

    requirement_entity_ref_max = (
        _MAX_ENTITIES
        if has_context_entities
        else 0
    )

    resolution_max = (
        _MAX_RESOLUTIONS
        if has_context_entities
        else 0
    )

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "outcome",
            "requirements",
            "resolved_references",
            "topic",
            "clarification_question",
        ],
        "properties": {
            "outcome": {
                "type": "string",
                "enum": [
                    "plan",
                    "clarify",
                    "conversation",
                ],
            },
            "requirements": {
                "type": "array",
                "maxItems": _MAX_REQUIREMENTS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "capability_id",
                        "purpose",
                        "entity_refs",
                    ],
                    "properties": {
                        "capability_id": {
                            "type": "string",
                            "enum": list(capability_ids),
                        },
                        "purpose": {
                            "type": "string",
                            "maxLength": _MAX_LABEL_CHARS,
                        },
                        "entity_refs": {
                            "type": "array",
                            "uniqueItems": True,
                            "maxItems": requirement_entity_ref_max,
                            "items": entity_ref_schema,
                        },
                    },
                },
            },
            "resolved_references": {
                "type": "array",
                "maxItems": resolution_max,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "mention",
                        "entity_ref",
                        "basis",
                    ],
                    "properties": {
                        "mention": {
                            "type": "string",
                            "maxLength": _MAX_LABEL_CHARS,
                        },
                        "entity_ref": entity_ref_schema,
                        "basis": {
                            "type": "string",
                            "maxLength": _MAX_LABEL_CHARS,
                        },
                    },
                },
            },
            "topic": {
                "type": ["string", "null"],
                "maxLength": _MAX_LABEL_CHARS,
            },
            "clarification_question": {
                "type": ["string", "null"],
                "maxLength": 800,
            },
        },
    }


def _validate_plan(
    proposal: Mapping[str, Any], *, offered_ids: set[str], known_refs: set[str]
) -> DynamicConversationPlan:
    outcome = str(proposal.get("outcome", "")).strip()
    raw_requirements = proposal.get("requirements", ())
    raw_resolutions = proposal.get("resolved_references", ())
    if not isinstance(raw_requirements, Sequence) or isinstance(raw_requirements, (str, bytes)):
        raise DynamicConversationPlanError("requirements must be an array")
    if not isinstance(raw_resolutions, Sequence) or isinstance(raw_resolutions, (str, bytes)):
        raise DynamicConversationPlanError("resolved_references must be an array")

    requirements: list[DynamicCapabilityRequirement] = []
    for raw in raw_requirements:
        if not isinstance(raw, Mapping):
            raise DynamicConversationPlanError("capability requirement must be an object")
        capability_id = str(raw.get("capability_id", "")).strip()
        if capability_id not in offered_ids:
            raise DynamicConversationPlanError("model selected a capability that was not offered")
        raw_refs = raw.get("entity_refs", ())
        if not isinstance(raw_refs, Sequence) or isinstance(raw_refs, (str, bytes)):
            raise DynamicConversationPlanError("capability entity_refs must be an array")
        refs = tuple(dict.fromkeys(str(item).strip() for item in raw_refs if str(item).strip()))
        if any(ref not in known_refs for ref in refs):
            raise DynamicConversationPlanError("capability requirement referenced an unknown entity")
        requirements.append(
            DynamicCapabilityRequirement(
                capability_id=capability_id,
                purpose=str(raw.get("purpose", "")).strip(),
                entity_refs=refs,
            )
        )

    resolutions: list[ConversationReferenceResolution] = []
    for raw in raw_resolutions:
        if not isinstance(raw, Mapping):
            raise DynamicConversationPlanError("reference resolution must be an object")
        ref = str(raw.get("entity_ref", "")).strip()
        if ref not in known_refs:
            raise DynamicConversationPlanError("model resolved a reference to an unknown entity")
        resolutions.append(
            ConversationReferenceResolution(
                mention=str(raw.get("mention", "")).strip(),
                entity_ref=ref,
                basis=str(raw.get("basis", "")).strip(),
            )
        )

    topic_value = proposal.get("topic")
    topic = None if topic_value is None else str(topic_value).strip() or None
    clarification_value = proposal.get("clarification_question")
    clarification = (
        None if clarification_value is None else str(clarification_value).strip() or None
    )

    # Clarification is a stop decision. A structured model can occasionally
    # emit capability requirements while also declaring that clarification is
    # required. Requirements must never execute in that state. Discard them
    # and preserve the clarification so the conversational layer can ask the
    # human naturally instead of turning a safe stop into a runtime failure.
    #
    # This normalization does not choose a provider, capability, target, or
    # fact. It removes execution requests from a non-executable outcome.
    if outcome == "clarify" and requirements:
        requirements = []

    # A structured model can occasionally emit the conversational label while
    # simultaneously selecting one or more governed capabilities. Those two
    # fields are contradictory: by contract, "conversation" means that no
    # capability invocation is required. When concrete requirements are
    # present, treat them as the stronger structural signal and normalize the
    # outcome to "plan". This does not choose a capability, provider, target,
    # or fact; every requirement has already been bounded to the runtime-
    # offered catalog and remains subject to Central Orchestrator governance.
    #
    # Never perform this normalization for "clarify": ambiguity must continue
    # to block execution even if a model also emitted capability requirements.
    if outcome == "conversation" and requirements:
        outcome = "plan"

    # clarification_question is meaningful only for a clarify outcome.
    # A bounded model can emit a valid governed plan while also populating
    # the required nullable clarification field with stray text. Once the
    # final structural outcome is "plan", concrete validated requirements
    # are the controlling signal and the contradictory clarification text
    # is discarded. This does not choose a capability, provider, target,
    # fact, or argument; all requirements were already bounded to the
    # runtime-offered catalog and remain subject to normal governance.
    #
    # Do not apply this to "conversation". A conversational outcome carrying
    # a clarification remains contradictory and continues to fail closed.
    if outcome == "plan" and clarification is not None:
        clarification = None

    return DynamicConversationPlan(
        outcome=outcome,
        requirements=tuple(requirements),
        resolved_references=tuple(resolutions),
        topic=topic,
        clarification_question=clarification,
    )
