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
    clarification_basis: str | None = None
    conversation_response: str | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {"plan", "clarify", "conversation"}:
            raise DynamicConversationPlanError("dynamic conversation outcome is invalid")
        if len(self.requirements) > _MAX_REQUIREMENTS:
            raise DynamicConversationPlanError("dynamic capability plan exceeds safety bound")
        if self.outcome == "plan" and not self.requirements:
            raise DynamicConversationPlanError("plan outcome requires at least one capability")
        if self.outcome != "plan" and self.requirements:
            raise DynamicConversationPlanError("non-plan outcome cannot execute capabilities")
        if self.clarification_basis not in {
            None,
            "none",
            "human_semantic",
            "internal_planning",
        }:
            raise DynamicConversationPlanError(
                "dynamic clarification basis is invalid"
            )

        if self.outcome == "clarify":
            if not self.clarification_question or not self.clarification_question.strip():
                raise DynamicConversationPlanError("clarify outcome requires a question")
        elif self.clarification_question is not None:
            raise DynamicConversationPlanError("only clarify outcome may carry a clarification question")
        if self.outcome == "conversation":
            if self.conversation_response is not None:
                response = self.conversation_response.strip()
                if not response or len(response) > 1600:
                    raise DynamicConversationPlanError(
                        "conversation response is empty or exceeds safety bound"
                    )
        elif self.conversation_response is not None:
            raise DynamicConversationPlanError(
                "only conversation outcome may carry a conversation response"
            )


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
            "capabilities": [item.model_view() for item in offered],
        }
        proposal = self.client.complete(
            system=_SYSTEM_INSTRUCTIONS,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=schema,
            max_output_tokens=512,
        )
        # FIRST_PASS_GROUNDED_HUMAN_AMBIGUITY
        if (
            str(
                proposal.get(
                    "outcome",
                    "",
                )
            ).strip()
            == "clarify"
            and str(
                proposal.get(
                    "clarification_basis",
                    "none",
                )
            ).strip()
            == "human_semantic"
            and not _human_clarification_is_grounded(
                proposal,
                human_text=clean_text,
                known_refs=set(known_refs),
            )
        ):
            # The model invented at least part of the alleged human choice.
            # Treat it as internal planning so the bounded retry resolves it
            # instead of surfacing it to the human.
            proposal=dict(proposal)
            proposal[
                "clarification_basis"
            ]="internal_planning"

        validated = _validate_plan(
            proposal,
            offered_ids=set(ids),
            known_refs=set(known_refs),
        )

        if (
            validated.outcome == "clarify"
            and validated.clarification_basis
            == "internal_planning"
        ):
            retry_payload = {
                **payload,
                "prior_internal_planning_attempt": {
                    "question": (
                        validated.clarification_question
                    ),
                    "instruction": (
                        "Resolve this internal planning choice yourself "
                        "from the offered governed capability contracts. "
                        "Do not ask the human to choose an evidence source, "
                        "provider, capability, record type, API, or retrieval "
                        "strategy. Return a plan unless a separate genuine "
                        "human semantic ambiguity remains."
                    ),
                },
            }

            retry_proposal = self.client.complete(
                system=_INTERNAL_PLANNING_RETRY_INSTRUCTIONS,
                user=json.dumps(
                    retry_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                schema=schema,
                max_output_tokens=512,
            )

            # RETRY_GROUNDED_HUMAN_AMBIGUITY
            if (
                str(
                    retry_proposal.get(
                        "outcome",
                        "",
                    )
                ).strip()
                == "clarify"
                and str(
                    retry_proposal.get(
                        "clarification_basis",
                        "none",
                    )
                ).strip()
                == "human_semantic"
                and not _human_clarification_is_grounded(
                    retry_proposal,
                    human_text=clean_text,
                    known_refs=set(known_refs),
                )
            ):
                retry_proposal=dict(
                    retry_proposal
                )
                retry_proposal[
                    "clarification_basis"
                ]="internal_planning"

            validated = _validate_plan(
                retry_proposal,
                offered_ids=set(ids),
                known_refs=set(known_refs),
            )

            if (
                validated.outcome == "clarify"
                and validated.clarification_basis
                == "internal_planning"
            ):
                raise DynamicConversationPlanError(
                    "planner could not resolve an internal "
                    "capability/evidence choice without human input"
                )

        return validated


_SYSTEM_INSTRUCTIONS = """You are Jason's bounded conversational planner. Interpret the human message using only the supplied conversation context and the self-describing governed capabilities supplied for this turn. There are no hidden phrase-to-provider, synonym, question-to-field, or fact mappings. Resolve references such as pronouns only when the supplied context supports the resolution. Select capabilities by their runtime descriptions and schemas, not by hard-coded provider assumptions. A capability selection is only a request to the Central Orchestrator; it does not grant authority and does not supply factual evidence. Never invent operational facts, entity identifiers, capabilities, provider results, completed actions, or authority. Do not ask the human to choose or provide an internal provider, registry, log, evidence source, or evidence location when an offered governed read/search capability can inspect the clearly identified resource. Uncertainty about whether a requested fact exists in returned evidence is not material ambiguity. A search capability may explicitly declare selector_required=false and a collection_scope. When the human requests that authorized collection as a whole, absence of a selector is intentional collection scope, not unresolved target ambiguity. Do not ask the human to narrow a collection-wide request merely because the capability also accepts optional selectors. For a clear factual read, select the best matching provider-neutral read/search capability using its resource types, business purpose, operation, and selectors, then let downstream governed evidence interpretation determine whether the requested fact is actually supported. Do not substitute a more specialized evidence collection merely because it might contain the fact when a primary resource read or search structurally matches the human's target. When a primary capability can read or enumerate the requested authorized resource set, execute that primary capability first and let downstream evidence fulfillment determine whether specialized expansion is necessary. The existence of several possible downstream evidence sources is an internal planning concern and must not be converted into a human clarification. Classify every clarification by basis. clarification_basis=human_semantic means the human must choose because the target, requested meaning, authority, action, or risk would materially differ. Every human_semantic clarification must include clarification_choices describing at least two plausible alternatives. Each alternative must be grounded either in an exact substring of the current human message or in a verified conversation entity. Never invent an unmentioned site, scope, resource, target, authority choice, action, or evidence strategy merely to create an alternative. clarification_basis=internal_planning means the human meaning is already sufficient and the remaining uncertainty is only which capability, provider evidence, record type, collection, API, or retrieval strategy Jason should use. Internal-planning uncertainty is Jason's responsibility and must not normally become a human-facing question. If choosing among plausible human meanings would materially change the target, authority, requested action, risk, or meaning, return clarify with clarification_basis=human_semantic and one concise natural clarification question. Otherwise return the complete bounded plan needed for the user's request with clarification_basis=none. If only an internal planning choice remains on the first pass, mark that clarify proposal clarification_basis=internal_planning so the runtime can require you to resolve it internally before anything is shown to the human. Use conversation only when no capability invocation is required. For a conversation outcome, provide a concise, natural human-facing conversation_response that does not claim operational evidence or action. Return only the structured object required by the schema."""


_INTERNAL_PLANNING_RETRY_INSTRUCTIONS = """You are Jason's bounded conversational planner performing a second pass because your prior proposal identified only internal planning uncertainty.

The human must not be asked to choose among providers, capabilities, evidence sources, record types, collections, APIs, logs, or retrieval strategies.

Use only the governed capabilities supplied in the payload.

Prefer a primary resource read or search that structurally matches the human's target. If that capability supports the authorized collection requested by the human, use it without manufacturing a selector. Let downstream governed evidence interpretation and evidence-gap expansion determine whether more specialized evidence is later needed.

Return outcome=plan when the human meaning is sufficient to begin governed evidence acquisition.

Return outcome=clarify with clarification_basis=human_semantic only if a separate unresolved human choice would materially change target, meaning, authority, action, or risk. Include at least two clarification_choices, and ground every choice in an exact human-message substring or a verified conversation entity. An alternative that exists only in your own reasoning is not a human ambiguity.

Do not invent facts, identifiers, capability names, authority, or provider results.

Return only the structured object required by the schema."""


def _plan_schema(capability_ids: tuple[str, ...], entity_refs: tuple[str, ...]) -> Mapping[str, Any]:
    entity_ref_schema: dict[str, Any] = {"type": "string"}
    if entity_refs:
        entity_ref_schema["enum"] = list(entity_refs)
    else:
        # No existing entities means contextual references cannot be claimed.
        entity_ref_schema["enum"] = []
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "outcome", "requirements", "resolved_references", "topic", "clarification_question", "clarification_basis", "clarification_choices", "conversation_response"
        ],
        "properties": {
            "outcome": {"type": "string", "enum": ["plan", "clarify", "conversation"]},
            "requirements": {
                "type": "array",
                "maxItems": _MAX_REQUIREMENTS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["capability_id", "purpose", "entity_refs"],
                    "properties": {
                        "capability_id": {"type": "string", "enum": list(capability_ids)},
                        "purpose": {"type": "string", "maxLength": _MAX_LABEL_CHARS},
                        "entity_refs": {
                            "type": "array", "uniqueItems": True, "maxItems": _MAX_ENTITIES,
                            "items": entity_ref_schema,
                        },
                    },
                },
            },
            "resolved_references": {
                "type": "array",
                "maxItems": _MAX_RESOLUTIONS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["mention", "entity_ref", "basis"],
                    "properties": {
                        "mention": {"type": "string", "maxLength": _MAX_LABEL_CHARS},
                        "entity_ref": entity_ref_schema,
                        "basis": {"type": "string", "maxLength": _MAX_LABEL_CHARS},
                    },
                },
            },
            "topic": {"type": ["string", "null"], "maxLength": _MAX_LABEL_CHARS},
            "clarification_question": {"type": ["string", "null"], "maxLength": 800},
            "clarification_basis": {
                "type": "string",
                "enum": [
                    "none",
                    "human_semantic",
                    "internal_planning",
                ],
            },
            "clarification_choices": {
                "type": "array",
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "label",
                        "source_type",
                        "entity_ref",
                        "literal",
                    ],
                    "properties": {
                        "label": {
                            "type": "string",
                            "maxLength": 256,
                        },
                        "source_type": {
                            "type": "string",
                            "enum": [
                                "literal",
                                "entity",
                            ],
                        },
                        "entity_ref": {
                            "type": [
                                "string",
                                "null",
                            ],
                            "maxLength": 256,
                        },
                        "literal": {
                            "type": [
                                "string",
                                "null",
                            ],
                            "maxLength": 512,
                        },
                    },
                },
            },
            "conversation_response": {"type": ["string", "null"], "maxLength": 1600},
        },
    }


def _human_clarification_is_grounded(
    proposal: Mapping[str, Any],
    *,
    human_text: str,
    known_refs: set[str],
) -> bool:
    """Require human clarification alternatives to come from human/context evidence.

    A model may not manufacture a new site, scope, target, authority choice,
    action, resource, or interpretation and then ask the human to choose it.
    Genuine human ambiguity requires at least two plausible alternatives, and
    every alternative must be grounded either in an exact substring of the
    current human message or in an already-verified conversation entity.

    Several interpretations may cite the same literal. That preserves cases
    where one human phrase is genuinely ambiguous while preventing an invented
    alternative from becoming a user-facing clarification.
    """

    raw_choices = proposal.get(
        "clarification_choices",
        (),
    )

    if (
        not isinstance(
            raw_choices,
            Sequence,
        )
        or isinstance(
            raw_choices,
            (
                str,
                bytes,
            ),
        )
        or len(raw_choices) < 2
        or len(raw_choices) > 8
    ):
        return False

    grounded_count=0

    for raw in raw_choices:
        if not isinstance(
            raw,
            Mapping,
        ):
            return False

        label=str(
            raw.get(
                "label",
                "",
            )
        ).strip()

        source_type=str(
            raw.get(
                "source_type",
                "",
            )
        ).strip()

        entity_ref=raw.get(
            "entity_ref"
        )

        literal=raw.get(
            "literal"
        )

        if not label:
            return False

        if source_type == "literal":
            if entity_ref is not None:
                return False

            if literal is None:
                return False

            value=str(
                literal
            )

            if (
                not value
                or len(value) > 512
                or value not in human_text
            ):
                return False

        elif source_type == "entity":
            if literal is not None:
                return False

            if entity_ref is None:
                return False

            ref=str(
                entity_ref
            ).strip()

            if ref not in known_refs:
                return False

        else:
            return False

        grounded_count += 1

    return grounded_count >= 2


def _validate_plan(
    proposal: Mapping[str, Any], *, offered_ids: set[str], known_refs: set[str]
) -> DynamicConversationPlan:
    outcome = str(proposal.get("outcome", "")).strip()
    raw_requirements = proposal.get("requirements", ())
    raw_resolutions = proposal.get("resolved_references", ())
    raw_clarification_choices = proposal.get(
        "clarification_choices",
        (),
    )
    if not isinstance(raw_requirements, Sequence) or isinstance(raw_requirements, (str, bytes)):
        raise DynamicConversationPlanError("requirements must be an array")
    if not isinstance(raw_resolutions, Sequence) or isinstance(raw_resolutions, (str, bytes)):
        raise DynamicConversationPlanError("resolved_references must be an array")
    if (
        not isinstance(
            raw_clarification_choices,
            Sequence,
        )
        or isinstance(
            raw_clarification_choices,
            (
                str,
                bytes,
            ),
        )
    ):
        raise DynamicConversationPlanError(
            "clarification_choices must be an array"
        )
    if len(raw_clarification_choices) > 8:
        raise DynamicConversationPlanError(
            "clarification choice count exceeds safety bound"
        )

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
    clarification_basis = str(
        proposal.get(
            "clarification_basis",
            "none",
        )
    ).strip()

    if clarification_basis not in {
        "none",
        "human_semantic",
        "internal_planning",
    }:
        raise DynamicConversationPlanError(
            "clarification_basis is invalid"
        )

    response_value = proposal.get("conversation_response")
    conversation_response = (
        None if response_value is None else str(response_value).strip() or None
    )

    # Clarification choices never influence execution authority.
    # They exist only to prove that a human-facing ambiguity is grounded.
    if outcome != "clarify" and raw_clarification_choices:
        raise DynamicConversationPlanError(
            "only clarify outcome may carry clarification choices"
        )

    # Normalize clarification basis against the declared outcome.
    # Internal planning uncertainty is never silently converted into
    # human semantic ambiguity.
    if outcome != "clarify":
        clarification_basis = "none"
    elif clarification_basis == "none":
        clarification_basis = "human_semantic"

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
        conversation_response = None

    return DynamicConversationPlan(
        outcome=outcome,
        requirements=tuple(requirements),
        resolved_references=tuple(resolutions),
        topic=topic,
        clarification_question=clarification,
        clarification_basis=clarification_basis,
        conversation_response=conversation_response,
    )
