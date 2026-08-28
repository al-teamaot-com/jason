"""Quality gate for clarification and conversation-only Teams text.

The Conversation Kernel may propose human-facing wording, but that wording is not
released directly. Jason first applies deterministic internal-identifier checks and a
bounded experience review. A rejected candidate can be rewritten by the configured
low-cost-to-strong reasoning pool without changing the already-decided conversational
meaning or creating execution authority.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .conversation_kernel import ValidatedReasoningPool


_MAX_TEXT_CHARS = 2400


class ConversationTextQualityError(ValueError):
    """Conversation-only or clarification text failed the experience contract."""


@dataclass(frozen=True, slots=True)
class ConversationTextReview:
    approved: bool
    preserves_meaning: bool
    natural: bool
    exposes_internal_plumbing: bool
    adds_unsupported_operational_claims: bool


_REWRITE_INSTRUCTIONS = """You are Jason's bounded conversation wording step. Rewrite the supplied candidate only as needed to produce a natural, concise human-facing response while preserving the already-decided conversational meaning. Do not add operational facts, providers, connectors, capabilities, API details, model details, schemas, workflows, or execution claims. For a clarification, ask only the material question already expressed by the candidate; never ask the human to choose an internal evidence source or implementation path. For conversation-only text, do not invent system state or actions. Return only the required structured object."""

_REVIEW_INSTRUCTIONS = """You are Jason's bounded Conversation Experience text reviewer. Decide whether the candidate naturally and directly expresses the supplied already-decided conversational meaning, avoids internal implementation plumbing, and adds no unsupported operational facts or action claims. For clarification, ensure it asks only the material human ambiguity rather than asking about internal providers, evidence locations, registries, APIs, or tools. Do not rewrite the text. Return only the required structured object."""


@dataclass(frozen=True, slots=True)
class ConversationTextQualityGate:
    rewriting: ValidatedReasoningPool
    reviewing: ValidatedReasoningPool

    def finalize(
        self,
        *,
        human_text: str,
        kind: str,
        candidate: str,
        internal_identifiers: tuple[str, ...] = (),
    ) -> str:
        if kind not in {"clarification", "conversation"}:
            raise ValueError("conversation text kind is invalid")
        source = candidate.strip()
        if not source:
            raise ConversationTextQualityError("conversation candidate text is required")
        if len(source) > _MAX_TEXT_CHARS:
            raise ConversationTextQualityError("conversation candidate exceeds safety bound")

        if not _contains_internal_identifier(source, internal_identifiers):
            review = self._review(
                human_text=human_text,
                kind=kind,
                semantic_text=source,
                candidate=source,
            )
            if _review_passes(review):
                return source

        payload = {
            "human_message": human_text.strip(),
            "kind": kind,
            "already_decided_meaning": source,
        }
        rewritten, _ = self.rewriting.complete_validated(
            system=_REWRITE_INSTRUCTIONS,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["text"],
                "properties": {
                    "text": {
                        "type": "string",
                        "maxLength": _MAX_TEXT_CHARS,
                    }
                },
            },
            max_output_tokens=512,
            validator=lambda proposal: self._validate_rewrite(
                proposal=proposal,
                human_text=human_text,
                kind=kind,
                semantic_text=source,
                internal_identifiers=internal_identifiers,
            ),
        )
        return rewritten

    def _validate_rewrite(
        self,
        *,
        proposal: Mapping[str, Any],
        human_text: str,
        kind: str,
        semantic_text: str,
        internal_identifiers: tuple[str, ...],
    ) -> str:
        if not isinstance(proposal, Mapping) or set(proposal) != {"text"}:
            raise ConversationTextQualityError("conversation rewrite shape is invalid")
        text = str(proposal.get("text", "")).strip()
        if not text or len(text) > _MAX_TEXT_CHARS:
            raise ConversationTextQualityError("conversation rewrite text is invalid")
        if _contains_internal_identifier(text, internal_identifiers):
            raise ConversationTextQualityError(
                "conversation rewrite exposed an internal implementation identifier"
            )
        review = self._review(
            human_text=human_text,
            kind=kind,
            semantic_text=semantic_text,
            candidate=text,
        )
        if not _review_passes(review):
            raise ConversationTextQualityError(
                "conversation rewrite failed the experience quality review"
            )
        return text

    def _review(
        self,
        *,
        human_text: str,
        kind: str,
        semantic_text: str,
        candidate: str,
    ) -> ConversationTextReview:
        review, _ = self.reviewing.complete_validated(
            system=_REVIEW_INSTRUCTIONS,
            user=json.dumps(
                {
                    "human_message": human_text.strip(),
                    "kind": kind,
                    "already_decided_meaning": semantic_text,
                    "candidate": candidate,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "approved",
                    "preserves_meaning",
                    "natural",
                    "exposes_internal_plumbing",
                    "adds_unsupported_operational_claims",
                ],
                "properties": {
                    "approved": {"type": "boolean"},
                    "preserves_meaning": {"type": "boolean"},
                    "natural": {"type": "boolean"},
                    "exposes_internal_plumbing": {"type": "boolean"},
                    "adds_unsupported_operational_claims": {"type": "boolean"},
                },
            },
            max_output_tokens=192,
            validator=_validate_review,
        )
        return review


def _validate_review(proposal: Mapping[str, Any]) -> ConversationTextReview:
    required = {
        "approved",
        "preserves_meaning",
        "natural",
        "exposes_internal_plumbing",
        "adds_unsupported_operational_claims",
    }
    if not isinstance(proposal, Mapping) or set(proposal) != required:
        raise ConversationTextQualityError("conversation text review shape is invalid")
    for key in required:
        if not isinstance(proposal.get(key), bool):
            raise ConversationTextQualityError(
                "conversation text review booleans must be actual booleans"
            )
    return ConversationTextReview(
        approved=proposal["approved"],
        preserves_meaning=proposal["preserves_meaning"],
        natural=proposal["natural"],
        exposes_internal_plumbing=proposal["exposes_internal_plumbing"],
        adds_unsupported_operational_claims=proposal[
            "adds_unsupported_operational_claims"
        ],
    )


def _review_passes(review: ConversationTextReview) -> bool:
    return (
        review.approved
        and review.preserves_meaning
        and review.natural
        and not review.exposes_internal_plumbing
        and not review.adds_unsupported_operational_claims
    )


def _contains_internal_identifier(text: str, identifiers: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(
        identifier.strip()
        and identifier.strip().casefold() in folded
        for identifier in identifiers
    )
