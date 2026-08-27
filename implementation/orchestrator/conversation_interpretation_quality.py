"""Review-gated provider-independent interpretation for the Conversation Kernel.

A conversational model's structured interpretation is a proposal, not authority. This
wrapper validates grounding first, then asks an independent bounded reviewer whether the
proposal actually captures the human request at the correct abstraction. A rejected
proposal causes the proposing pool to try its next configured backend. No capability,
provider, connector, or execution metadata is introduced into either stage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .conversation_kernel import (
    ConversationKernelDecision,
    DynamicConversationContext,
    ReasoningAttempt,
    ValidatedReasoningPool,
    _FORBIDDEN_INTERNAL_KEYS,
    _MAX_TEXT_CHARS,
    _SYSTEM_INSTRUCTIONS,
    _decision_schema,
    _validate_decision,
)


class ConversationInterpretationQualityError(ValueError):
    """A structurally valid interpretation failed semantic conversation review."""


@dataclass(frozen=True, slots=True)
class ConversationInterpretationReview:
    approved: bool
    captures_human_request: bool
    targets_are_relevant: bool
    complete_bounded_request: bool
    clarification_policy_ok: bool
    clarification_requires_missing_human_input: bool
    clarification_material_choice: bool
    no_internal_routing: bool
    unsupported_operational_claim_risk: bool


_EXPERIENCE_INSTRUCTIONS = (
    _SYSTEM_INSTRUCTIONS
    + " The Conversation Experience information path is read-only. Jason owns read "
    "authority deterministically, so every information need uses observe authority. "
    "Do not use information needs to encode a requested action or higher authority. "
    "Verified conversation context is authoritative for reference resolution. "
    "The supplied active_entity_refs and active_entities identify Jason's current "
    "verified conversational focus by resource kind. When the human naturally refers "
    "to the current subject without naming it again and exactly one relevant active "
    "entity resolves that subject, use that verified entity instead of asking the human "
    "to repeat the target. For target_source verified_entity, copy target_entity_ref "
    "exactly from entity_ref, target_kind exactly from kind, and target_reference exactly "
    "from canonical_id or display_name. Clarification is only for a specific missing "
    "human choice or input that cannot be resolved from verified conversation context or "
    "discovered through governed evidence and whose value would materially change target, "
    "authority, action, risk, or meaning. Broad or open-ended read scope is not itself "
    "material ambiguity. Never ask the human a question whose answer Jason is expected "
    "to discover from governed evidence, never ask the human to repeat a target already "
    "resolved by verified context, and never merely restate the human's information "
    "request as a clarification."
)

_REVIEW_INSTRUCTIONS = """You are Jason's independent Conversation Kernel interpretation reviewer. Review a provider-independent interpretation against the human message and verified conversation context. Do not choose providers, connectors, capabilities, APIs, tools, evidence locations, or implementation paths. Assess each requested dimension independently; the approved field is advisory only because Jason deterministically owns the final review verdict. For information outcomes, assess whether the interpretation captures what the human actually wants, uses relevant grounded targets, and includes the complete bounded request. For ordinary conversation outcomes, assess whether the response captures the human turn without unsupported operational claims. For clarification outcomes, determine whether a specific human-supplied discriminator or choice is genuinely missing after considering verified conversation context and governed discoverability, and whether choosing without it would materially change target, authority, action, risk, or meaning. The supplied active_entity_refs and active_entities are verified Jason-owned conversational focus; a clarification must not ask the human to repeat a target already resolved by exactly one relevant active entity. Broad, open-ended, or comprehensive read scope is not itself material ambiguity. A clarification must not merely restate or paraphrase the human's requested information, ask the human to answer Jason's own factual lookup question, or request an internal evidence source or implementation choice. If the missing human input selects among possible targets, clarification_material_choice is true because selecting an otherwise unresolved target is material: the human choice changes the target. For non-clarification outcomes, clarification_requires_missing_human_input and clarification_material_choice are not applicable. Generic target/completeness fields may be not applicable before a target has been selected and do not override the two clarification-specific dimensions. Information outcomes are read-only; reject any requested action represented as an information outcome. Conversation-only outcomes must not assert unverified operational state or claim that an action occurred. Do not repair the interpretation. Return only the required structured object."""


@dataclass(frozen=True, slots=True)
class ReviewedConversationKernel:
    """Conversation Kernel boundary with independent semantic quality review.

    ``resource_kinds`` is a runtime-owned provider-neutral vocabulary source. It exposes
    only structural resource kinds that the governed fulfillment catalog can actually
    start from. Capability IDs, providers, connectors, and execution details remain
    outside the Conversation Kernel. The callable is evaluated on every turn so future
    registered resources become available without prompt patches or static mappings.
    """

    proposing: ValidatedReasoningPool
    reviewing: ValidatedReasoningPool
    resource_kinds: Callable[[], tuple[str, ...]] | None = None
    resource_descriptions: Callable[[], Mapping[str, str]] | None = None

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
        runtime_resource_kinds = _normalize_resource_kinds(self.resource_kinds)
        runtime_resource_descriptions = _normalize_resource_descriptions(
            self.resource_descriptions,
            allowed_resource_kinds=runtime_resource_kinds,
        )
        payload: dict[str, Any] = {
            "message": clean_text,
            "context": _context_payload(context),
        }
        if self.resource_kinds is not None:
            payload["available_resource_kinds"] = list(runtime_resource_kinds)
        if runtime_resource_descriptions:
            payload["resource_kind_descriptions"] = dict(
                runtime_resource_descriptions
            )

        schema = _decision_schema(known_refs)
        information_properties = schema["properties"]["information_needs"]["items"][
            "properties"
        ]
        information_properties["authority"]["enum"] = ["observe"]
        if self.resource_kinds is not None and runtime_resource_kinds:
            information_properties["target_kind"]["enum"] = list(runtime_resource_kinds)

        return self.proposing.complete_validated(
            system=_EXPERIENCE_INSTRUCTIONS,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=schema,
            max_output_tokens=768,
            validator=lambda proposal: self._validate_and_review(
                proposal=proposal,
                text=clean_text,
                context=context,
                context_payload=payload["context"],
                allowed_resource_kinds=(
                    runtime_resource_kinds
                    if self.resource_kinds is not None
                    else None
                ),
            ),
        )

    def _validate_and_review(
        self,
        *,
        proposal: Mapping[str, Any],
        text: str,
        context: DynamicConversationContext,
        context_payload: Mapping[str, Any],
        allowed_resource_kinds: tuple[str, ...] | None,
    ) -> ConversationKernelDecision:
        normalized = _normalize_experience_proposal(proposal, context=context)
        decision = _validate_decision(
            proposal=normalized,
            text=text,
            context=context,
        )
        if allowed_resource_kinds is not None and decision.outcome == "information":
            allowed = set(allowed_resource_kinds)
            unknown = sorted(
                {
                    item.target.kind
                    for item in decision.information_needs
                    if item.target.kind not in allowed
                }
            )
            if unknown:
                raise ConversationInterpretationQualityError(
                    "conversation interpretation selected an unregistered resource kind"
                )

        review_payload = {
            "human_message": text,
            "verified_context": context_payload,
            "proposed_interpretation": _decision_payload(decision),
        }
        if allowed_resource_kinds is not None:
            review_payload["available_resource_kinds"] = list(
                allowed_resource_kinds
            )
        runtime_resource_descriptions = _normalize_resource_descriptions(
            self.resource_descriptions,
            allowed_resource_kinds=(
                allowed_resource_kinds or ()
            ),
        )
        if runtime_resource_descriptions:
            review_payload["resource_kind_descriptions"] = dict(
                runtime_resource_descriptions
            )
        review, _ = self.reviewing.complete_validated(
            system=_REVIEW_INSTRUCTIONS,
            user=json.dumps(review_payload, ensure_ascii=False, separators=(",", ":")),
            schema=_review_schema(),
            max_output_tokens=256,
            validator=_validate_review,
        )
        if _review_failed_for_outcome(review=review, outcome=decision.outcome):
            raise ConversationInterpretationQualityError(
                "conversation interpretation failed a required quality dimension"
            )
        return decision


def _review_failed_for_outcome(
    *,
    review: ConversationInterpretationReview,
    outcome: str,
) -> bool:
    """Apply semantic review dimensions only where they are meaningful.

    The reviewer returns bounded semantic observations, not Jason's final governance
    verdict. Jason derives pass/fail deterministically so an aggregate model opinion
    cannot override outcome-specific policy dimensions.
    """

    if not review.no_internal_routing or review.unsupported_operational_claim_risk:
        return True

    if outcome == "clarify":
        return (
            not review.clarification_requires_missing_human_input
            or not review.clarification_material_choice
        )

    if outcome == "information":
        return (
            not review.captures_human_request
            or not review.targets_are_relevant
            or not review.complete_bounded_request
        )

    if outcome == "conversation":
        return not review.captures_human_request

    return True


def _normalize_experience_proposal(
    proposal: Mapping[str, Any],
    *,
    context: DynamicConversationContext | None = None,
) -> Mapping[str, Any]:
    """Project advisory model output onto Jason's mutually exclusive turn contract.

    Outcome-exclusive fields are projected before validation. Information read authority
    is Jason-owned. When a model selects a verified entity, the entity's resource kind is
    also Jason-owned metadata and is projected from verified conversation state.
    """
    if not isinstance(proposal, Mapping):
        return proposal

    _reject_internal_routing_even_if_discarded(proposal)
    normalized: dict[str, Any] = dict(proposal)
    outcome = str(normalized.get("outcome", "")).strip().casefold()
    verified_entities = (
        {entity.ref: entity for entity in context.entities}
        if context is not None
        else {}
    )

    if outcome == "information":
        normalized["clarification_question"] = None
        normalized["conversational_response"] = None
        raw_needs = normalized.get("information_needs", ())
        if isinstance(raw_needs, Sequence) and not isinstance(raw_needs, (str, bytes)):
            needs: list[Any] = []
            for raw in raw_needs:
                if isinstance(raw, Mapping):
                    item = dict(raw)
                    item["authority"] = "observe"
                    source = str(item.get("target_source", "")).strip().casefold()
                    raw_entity_ref = item.get("target_entity_ref")
                    entity_ref = (
                        None
                        if raw_entity_ref is None
                        else str(raw_entity_ref).strip() or None
                    )
                    if source == "verified_entity" and entity_ref in verified_entities:
                        item["target_kind"] = verified_entities[entity_ref].kind
                    needs.append(item)
                else:
                    needs.append(raw)
            normalized["information_needs"] = needs
    elif outcome == "clarify":
        normalized["information_needs"] = []
        normalized["conversational_response"] = None
    elif outcome == "conversation":
        normalized["information_needs"] = []
        normalized["clarification_question"] = None

    return normalized


def _reject_internal_routing_even_if_discarded(proposal: Mapping[str, Any]) -> None:
    forbidden = sorted(_FORBIDDEN_INTERNAL_KEYS.intersection(str(key) for key in proposal))
    if forbidden:
        raise ConversationInterpretationQualityError(
            "conversation interpretation attempted internal execution selection"
        )
    raw_needs = proposal.get("information_needs", ())
    if not isinstance(raw_needs, Sequence) or isinstance(raw_needs, (str, bytes)):
        return
    for raw in raw_needs:
        if not isinstance(raw, Mapping):
            continue
        forbidden = sorted(_FORBIDDEN_INTERNAL_KEYS.intersection(str(key) for key in raw))
        if forbidden:
            raise ConversationInterpretationQualityError(
                "conversation interpretation attempted internal execution selection"
            )


def _normalize_resource_kinds(
    source: Callable[[], tuple[str, ...]] | None,
) -> tuple[str, ...]:
    if source is None:
        return ()
    raw = source()
    if isinstance(raw, (str, bytes)):
        raise ConversationInterpretationQualityError(
            "runtime resource vocabulary must be a collection"
        )
    normalized = tuple(
        sorted({str(item).strip() for item in raw if str(item).strip()})
    )
    if len(normalized) > 256:
        raise ConversationInterpretationQualityError(
            "runtime resource vocabulary exceeds safety bound"
        )
    return normalized


def _normalize_resource_descriptions(
    source: Callable[[], Mapping[str, str]] | None,
    *,
    allowed_resource_kinds: tuple[str, ...],
) -> Mapping[str, str]:
    if source is None:
        return {}

    raw = source()

    if not isinstance(raw, Mapping):
        raise ConversationInterpretationQualityError(
            "runtime resource descriptions must be a mapping"
        )

    allowed = set(allowed_resource_kinds)
    normalized: dict[str, str] = {}

    for raw_kind, raw_description in raw.items():
        kind = str(raw_kind).strip()
        description = " ".join(
            str(raw_description).split()
        )

        if not kind or not description:
            continue

        if allowed and kind not in allowed:
            raise ConversationInterpretationQualityError(
                "runtime resource description references an unavailable resource kind"
            )

        if len(description) > 2048:
            raise ConversationInterpretationQualityError(
                "runtime resource description exceeds safety bound"
            )

        normalized[kind] = description

    if len(normalized) > 256:
        raise ConversationInterpretationQualityError(
            "runtime resource descriptions exceed safety bound"
        )

    return {
        kind: normalized[kind]
        for kind in sorted(normalized)
    }


def _context_payload(context: DynamicConversationContext) -> Mapping[str, Any]:
    entities = {item.ref: item for item in context.entities}
    active_entities = []
    for kind, ref in sorted(context.active_entity_refs.items()):
        entity = entities[ref]
        active_entities.append(
            {
                "kind": kind,
                "entity_ref": entity.ref,
                "canonical_id": entity.canonical_id,
                "display_name": entity.display_name,
            }
        )
    return {
        "conversation_id": context.conversation_id,
        "organization_id": context.organization_id,
        "principal_id": context.principal_id,
        "active_topic": context.active_topic,
        "active_entity_refs": dict(context.active_entity_refs),
        "active_entities": active_entities,
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
    }


def _decision_payload(decision: ConversationKernelDecision) -> Mapping[str, Any]:
    return {
        "outcome": decision.outcome,
        "information_needs": [
            {
                "target": {
                    "kind": item.target.kind,
                    "source": item.target.source,
                    "reference": item.target.reference,
                    "entity_ref": item.target.entity_ref,
                },
                "need": item.need,
                "authority": item.authority,
                "temporal_scope": item.temporal_scope,
                "completeness": item.completeness,
                "relationship": item.relationship,
            }
            for item in decision.information_needs
        ],
        "clarification_question": decision.clarification_question,
        "conversational_response": decision.conversational_response,
        "topic": decision.topic,
    }


def _review_schema() -> Mapping[str, Any]:
    properties = {
        "approved": {"type": "boolean"},
        "captures_human_request": {"type": "boolean"},
        "targets_are_relevant": {"type": "boolean"},
        "complete_bounded_request": {"type": "boolean"},
        "clarification_policy_ok": {"type": "boolean"},
        "clarification_requires_missing_human_input": {"type": "boolean"},
        "clarification_material_choice": {"type": "boolean"},
        "no_internal_routing": {"type": "boolean"},
        "unsupported_operational_claim_risk": {"type": "boolean"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def _validate_review(proposal: Mapping[str, Any]) -> ConversationInterpretationReview:
    required = {
        "approved",
        "captures_human_request",
        "targets_are_relevant",
        "complete_bounded_request",
        "clarification_policy_ok",
        "clarification_requires_missing_human_input",
        "clarification_material_choice",
        "no_internal_routing",
        "unsupported_operational_claim_risk",
    }
    if not isinstance(proposal, Mapping) or set(proposal) != required:
        raise ConversationInterpretationQualityError(
            "conversation interpretation review shape is invalid"
        )
    for key in required:
        if not isinstance(proposal.get(key), bool):
            raise ConversationInterpretationQualityError(
                "conversation interpretation review booleans must be actual booleans"
            )
    return ConversationInterpretationReview(
        approved=proposal["approved"],
        captures_human_request=proposal["captures_human_request"],
        targets_are_relevant=proposal["targets_are_relevant"],
        complete_bounded_request=proposal["complete_bounded_request"],
        clarification_policy_ok=proposal["clarification_policy_ok"],
        clarification_requires_missing_human_input=proposal[
            "clarification_requires_missing_human_input"
        ],
        clarification_material_choice=proposal["clarification_material_choice"],
        no_internal_routing=proposal["no_internal_routing"],
        unsupported_operational_claim_risk=proposal[
            "unsupported_operational_claim_risk"
        ],
    )
