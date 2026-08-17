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
    no_internal_routing: bool
    unsupported_operational_claim_risk: bool


_EXPERIENCE_INSTRUCTIONS = (
    _SYSTEM_INSTRUCTIONS
    + " The Conversation Experience information path is read-only. Jason owns read "
    "authority deterministically, so every information need uses observe authority. "
    "Do not use information needs to encode a requested action or higher authority."
)

_REVIEW_INSTRUCTIONS = """You are Jason's independent Conversation Kernel interpretation reviewer. Review a provider-independent interpretation against the human message and verified conversation context. Do not choose providers, connectors, capabilities, APIs, tools, evidence locations, or implementation paths. Approve only when the interpretation captures what the human actually wants, uses relevant grounded targets, includes the complete bounded request, and asks clarification only when choosing would materially change target, authority, action, risk, or meaning. Reject clarification about internal evidence sources or implementation choices. Information outcomes are read-only; reject any requested action represented as an information outcome. Conversation-only outcomes must not assert unverified operational state or claim that an action occurred. Do not repair the interpretation. Return only the required structured object."""


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
        payload: dict[str, Any] = {
            "message": clean_text,
            "context": _context_payload(context),
        }
        if self.resource_kinds is not None:
            payload["available_resource_kinds"] = list(runtime_resource_kinds)

        schema = _decision_schema(known_refs)
        information_properties = schema["properties"]["information_needs"]["items"][
            "properties"
        ]
        # Generation schemas are advisory, but do not ask a model to choose authority
        # Jason already owns. Canonical validation below remains the authority boundary.
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
        normalized = _normalize_experience_proposal(proposal)
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
        review, _ = self.reviewing.complete_validated(
            system=_REVIEW_INSTRUCTIONS,
            user=json.dumps(
                review_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_review_schema(),
            max_output_tokens=256,
            validator=_validate_review,
        )
        if not review.approved:
            raise ConversationInterpretationQualityError(
                "conversation interpretation did not pass independent quality review"
            )
        if (
            not review.captures_human_request
            or not review.targets_are_relevant
            or not review.complete_bounded_request
            or not review.clarification_policy_ok
            or not review.no_internal_routing
            or review.unsupported_operational_claim_risk
        ):
            raise ConversationInterpretationQualityError(
                "conversation interpretation failed a required quality dimension"
            )
        return decision


def _normalize_experience_proposal(
    proposal: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Project advisory model output onto Jason's mutually exclusive turn contract.

    Some structured-generation runtimes cannot express a true discriminated union, so a
    model can correctly choose an outcome while also filling fields belonging to another
    branch. The selected outcome is the structural discriminator; incompatible branch
    fields are non-authoritative generation noise. Semantic correctness is still judged
    independently after projection, and wrong discriminators remain invalid.

    Information authority is also not model-owned in this read-only Experience slice.
    It is fixed to ``observe`` before canonical validation and fulfillment.
    """

    if not isinstance(proposal, Mapping):
        return proposal

    _reject_internal_routing_even_if_discarded(proposal)

    normalized: dict[str, Any] = dict(proposal)
    outcome = str(normalized.get("outcome", "")).strip().casefold()

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
    """Do not let outcome projection hide an attempted internal-routing selection."""

    forbidden = sorted(
        _FORBIDDEN_INTERNAL_KEYS.intersection(str(key) for key in proposal)
    )
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
        forbidden = sorted(
            _FORBIDDEN_INTERNAL_KEYS.intersection(str(key) for key in raw)
        )
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
        sorted(
            {
                str(item).strip()
                for item in raw
                if str(item).strip()
            }
        )
    )
    if len(normalized) > 256:
        raise ConversationInterpretationQualityError(
            "runtime resource vocabulary exceeds safety bound"
        )
    return normalized


def _context_payload(context: DynamicConversationContext) -> Mapping[str, Any]:
    return {
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
        no_internal_routing=proposal["no_internal_routing"],
        unsupported_operational_claim_risk=proposal[
            "unsupported_operational_claim_risk"
        ],
    )
