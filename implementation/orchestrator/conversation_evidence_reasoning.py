"""Model-independent, review-gated raw evidence selection for conversations.

The model identifies only existing governed evidence locations. It does not decide
how values are calculated, normalized, or presented. A later bounded transformation
stage handles those concerns independently and deterministically.

This module contains no provider field map, fact vocabulary, synonym table, or
question-specific routing rule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .conversation_kernel import (
    ConversationKernelError,
    ValidatedReasoningPool,
)
from .dynamic_resource_response import (
    DynamicEvidenceSelection,
)
from .evidence_reference import (
    build_evidence_catalog,
    resolve_evidence_pointer,
    selectable_evidence_paths,
)


_MAX_SELECTED_PATHS = 32


class ConversationEvidenceReasoningError(
    ValueError
):
    """A proposed evidence selection or review was invalid."""


@dataclass(frozen=True, slots=True)
class EvidenceSelectionReview:
    approved: bool
    directly_supports_request: bool
    unavailable_is_justified: bool
    uses_adjacent_or_correlated_evidence: bool
    unsupported_claim_risk: bool


_SELECTION_INSTRUCTIONS = """You are Jason's bounded raw-evidence selector. Determine whether the provider-independent information need has complete raw support in the supplied sanitized governed evidence catalog.

Select only the smallest existing JSON Pointer path set that collectively supplies the raw evidence needed to answer the information need. When one existing value already contains the complete raw measurement or collection, do not also select a redundant alternative representation or its component values unless both are genuinely required to establish the requested information. The selected evidence does not have to be human-formatted or mathematically final: generic deterministic arithmetic, aggregation, or unit conversion may occur later. Do not perform or choose that transformation here.

A direct selection means only that the selected existing evidence paths are the complete raw inputs needed for the requested information. It does not mean the raw value is already answer-ready.

If the catalog has only partial, adjacent, correlated, or insufficient raw evidence, return unavailable with no paths so Jason may acquire more governed evidence.

Do not infer a missing operational value, substitute an adjacent field, invent a unit, use hidden mappings, or return an operational answer. Return paths only from the supplied evidence. Return only the required structured object."""

_REVIEW_INSTRUCTIONS = """You are Jason's independent raw-evidence selection reviewer. The provider-independent information need, sanitized evidence catalog, and proposed path selection are fixed.

For a direct proposal, approve only when the selected existing values collectively provide the complete raw inputs needed to establish the exact requested information. Reject redundant alternative representations when one selected measurement or one coherent component set is already sufficient. They may still require a later generic deterministic arithmetic, aggregation, or unit-conversion step. Reject a selection that represents only one component of a requested total, uses semantically adjacent or correlated evidence, includes unnecessary substitutes, or would require inventing a missing fact.

For unavailable, approve when the current catalog does not contain complete raw inputs for the requested information, including when useful partial evidence exists.

directly_supports_request means the selected raw inputs are complete for the information need, not that they are already human-formatted. unavailable_is_justified means additional governed evidence is required before a complete raw input set can be selected.

Do not calculate, transform, repair, or propose replacement paths. Return only the required structured object."""


@dataclass(frozen=True, slots=True)
class ValidatedConversationEvidenceReasoner:
    """Select raw evidence through bounded proposal and independent review."""

    selecting: ValidatedReasoningPool
    reviewing: ValidatedReasoningPool

    def select(
        self,
        *,
        question: str,
        sanitized_data: Any,
    ) -> DynamicEvidenceSelection:
        clean_question = question.strip()

        if not clean_question:
            raise ValueError(
                "conversation evidence question is required"
            )

        catalog = build_evidence_catalog(
            sanitized_data
        )

        selectable = selectable_evidence_paths(
            sanitized_data
        )

        if not selectable:
            return DynamicEvidenceSelection(
                answer_type="unavailable"
            )

        payload = {
            "information_need": clean_question,
            "evidence_catalog": catalog,
        }

        try:
            selection, _ = self.selecting.complete_validated(
                system=_SELECTION_INSTRUCTIONS,
                user=json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                schema=_selection_schema(
                    selectable
                ),
                max_output_tokens=256,
                validator=lambda proposal: self._validate_and_review(
                    proposal=proposal,
                    question=clean_question,
                    sanitized_data=sanitized_data,
                    catalog=catalog,
                    selectable=selectable,
                ),
            )
        except ConversationKernelError as error:
            # Bounded semantic evidence disagreement is a safe observational
            # outcome: Jason could not establish the requested fact from the
            # governed evidence with sufficient confidence. Convert only
            # evidence-reasoning validation exhaustion to unavailable. Do not
            # swallow connector, transport, authorization, or other runtime
            # failures.
            cause: BaseException | None = error

            while cause is not None:
                if isinstance(
                    cause,
                    ConversationEvidenceReasoningError,
                ):
                    return DynamicEvidenceSelection(
                        answer_type="unavailable"
                    )

                cause = cause.__cause__

            raise

        return selection

    def _validate_and_review(
        self,
        *,
        proposal: Mapping[str, Any],
        question: str,
        sanitized_data: Any,
        catalog: tuple[Mapping[str, Any], ...],
        selectable: tuple[str, ...],
    ) -> DynamicEvidenceSelection:
        selection = _validate_selection(
            proposal=proposal,
            selectable=selectable,
        )

        selected = [
            {
                "path": path,
                "value": resolve_evidence_pointer(
                    sanitized_data,
                    path,
                ),
            }
            for path in selection.evidence_paths
        ]

        review, _ = self.reviewing.complete_validated(
            system=_REVIEW_INSTRUCTIONS,
            user=json.dumps(
                {
                    "information_need": question,
                    "evidence_catalog": catalog,
                    "proposed": {
                        "answer_type": (
                            selection.answer_type
                        ),
                        "selected": selected,
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_review_schema(),
            max_output_tokens=256,
            validator=_validate_review,
        )

        if not review.approved:
            if (
                selection.answer_type == "direct"
                and review.unavailable_is_justified
                and not review.directly_supports_request
            ):
                return DynamicEvidenceSelection(
                    answer_type="unavailable"
                )

            raise ConversationEvidenceReasoningError(
                "evidence selection did not pass independent support review"
            )

        if selection.answer_type == "direct":
            if (
                not review.directly_supports_request
                or review.unavailable_is_justified
                or review.uses_adjacent_or_correlated_evidence
                or review.unsupported_claim_risk
            ):
                raise ConversationEvidenceReasoningError(
                    "direct evidence selection failed support quality dimensions"
                    f"; paths={selection.evidence_paths!r}"
                    f"; approved={review.approved}"
                    f"; directly_supports_request={review.directly_supports_request}"
                    f"; unavailable_is_justified={review.unavailable_is_justified}"
                    f"; uses_adjacent_or_correlated_evidence="
                    f"{review.uses_adjacent_or_correlated_evidence}"
                    f"; unsupported_claim_risk={review.unsupported_claim_risk}"
                )

        else:
            if (
                review.directly_supports_request
                or not review.unavailable_is_justified
                or review.unsupported_claim_risk
            ):
                raise ConversationEvidenceReasoningError(
                    "unavailable evidence decision failed support quality dimensions"
                )

        return selection


def _selection_schema(
    selectable: tuple[str, ...],
) -> Mapping[str, Any]:
    # Provider-derived paths are deliberately NOT embedded in the structured
    # response schema. Some legitimate provider keys contain arbitrary quoting
    # or shell-like text. Model output is bounded by deterministic validation
    # against `selectable` after generation instead.
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "answer_type",
            "evidence_paths",
        ],
        "properties": {
            "answer_type": {
                "type": "string",
                "enum": [
                    "direct",
                    "unavailable",
                ],
            },
            "evidence_paths": {
                "type": "array",
                "uniqueItems": True,
                "maxItems": _MAX_SELECTED_PATHS,
                "items": {
                    "type": "string",
                },
            },
        },
    }


def _review_schema() -> Mapping[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "approved",
            "directly_supports_request",
            "unavailable_is_justified",
            "uses_adjacent_or_correlated_evidence",
            "unsupported_claim_risk",
        ],
        "properties": {
            "approved": {
                "type": "boolean"
            },
            "directly_supports_request": {
                "type": "boolean"
            },
            "unavailable_is_justified": {
                "type": "boolean"
            },
            "uses_adjacent_or_correlated_evidence": {
                "type": "boolean"
            },
            "unsupported_claim_risk": {
                "type": "boolean"
            },
        },
    }


def _validate_selection(
    *,
    proposal: Mapping[str, Any],
    selectable: tuple[str, ...],
) -> DynamicEvidenceSelection:
    if not isinstance(
        proposal,
        Mapping,
    ):
        raise ConversationEvidenceReasoningError(
            "evidence selection must be an object"
        )

    if set(proposal) != {
        "answer_type",
        "evidence_paths",
    }:
        raise ConversationEvidenceReasoningError(
            "evidence selection shape is invalid"
        )

    answer_type = str(
        proposal.get(
            "answer_type",
            "",
        )
    ).strip().casefold()

    raw_paths = proposal.get(
        "evidence_paths",
        (),
    )

    if (
        not isinstance(raw_paths, Sequence)
        or isinstance(
            raw_paths,
            (str, bytes),
        )
    ):
        raise ConversationEvidenceReasoningError(
            "evidence_paths must be an array"
        )

    paths = tuple(
        dict.fromkeys(
            str(item).strip()
            for item in raw_paths
            if str(item).strip()
        )
    )

    if len(paths) > _MAX_SELECTED_PATHS:
        raise ConversationEvidenceReasoningError(
            "evidence path selection exceeds safety bound"
        )

    allowed = set(selectable)

    if any(
        path not in allowed
        for path in paths
    ):
        raise ConversationEvidenceReasoningError(
            "evidence selection used an unoffered path"
        )

    return DynamicEvidenceSelection(
        answer_type=answer_type,
        evidence_paths=paths,
    )


def _validate_review(
    proposal: Mapping[str, Any],
) -> EvidenceSelectionReview:
    required = {
        "approved",
        "directly_supports_request",
        "unavailable_is_justified",
        "uses_adjacent_or_correlated_evidence",
        "unsupported_claim_risk",
    }

    if (
        not isinstance(proposal, Mapping)
        or set(proposal) != required
    ):
        raise ConversationEvidenceReasoningError(
            "evidence support review shape is invalid"
        )

    for key in required:
        if not isinstance(
            proposal.get(key),
            bool,
        ):
            raise ConversationEvidenceReasoningError(
                "evidence support review booleans must be actual booleans"
            )

    if (
        proposal["directly_supports_request"]
        and proposal["unavailable_is_justified"]
    ):
        raise ConversationEvidenceReasoningError(
            "evidence support review cannot be both direct and unavailable"
        )

    return EvidenceSelectionReview(
        approved=proposal["approved"],
        directly_supports_request=proposal[
            "directly_supports_request"
        ],
        unavailable_is_justified=proposal[
            "unavailable_is_justified"
        ],
        uses_adjacent_or_correlated_evidence=proposal[
            "uses_adjacent_or_correlated_evidence"
        ],
        unsupported_claim_risk=proposal[
            "unsupported_claim_risk"
        ],
    )
