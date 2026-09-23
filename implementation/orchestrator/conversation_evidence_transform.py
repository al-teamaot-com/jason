"""Generic deterministic transformation of selected governed evidence.

Raw-evidence selection happens before this module. The transformation planner may
choose only a subset of that already-approved raw evidence, including descendants
of an approved container. It cannot reach outside the selected evidence roots.

The model chooses only an allowlisted generic operation and input paths. Jason
deterministically validates those paths and calculates the actual result.

There are no provider names, provider field mappings, endpoint fact mappings, or
question-specific rules in this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .conversation_kernel import ValidatedReasoningPool
from .evidence_sanitization import REDACTED


_ALLOWED_OPERATIONS = (
    "identity",
    "bytes_to_gib",
    "sum_bytes_to_gib",
    "unsupported",
)

_MAX_INPUT_PATHS = 64
_MAX_TRANSFORM_CANDIDATES = 256
_MAX_MODEL_STRING_CHARS = 512

_BYTES_PER_GIB = Decimal(1024) ** 3


class ConversationEvidenceTransformError(ValueError):
    """A bounded evidence transformation proposal was invalid."""


@dataclass(frozen=True, slots=True)
class TransformEvidence:
    path: str
    value: Any

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            raise ValueError(
                "transform evidence path must be an absolute JSON pointer"
            )


@dataclass(frozen=True, slots=True)
class EvidenceTransformPlan:
    operation: str
    input_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.operation not in _ALLOWED_OPERATIONS:
            raise ValueError(
                "evidence transform operation is not approved"
            )

        if len(self.input_paths) > _MAX_INPUT_PATHS:
            raise ValueError(
                "evidence transform input count exceeds safety bound"
            )


@dataclass(frozen=True, slots=True)
class EvidenceTransformReview:
    approved: bool
    operation_matches_evidence: bool
    produces_answer_ready_value: bool
    unsupported_is_justified: bool
    unsupported_claim_risk: bool


@dataclass(frozen=True, slots=True)
class ConversationEvidenceTransformResult:
    operation: str
    value: Any
    source_paths: tuple[str, ...]


_TRANSFORM_INSTRUCTIONS = """You are Jason's bounded evidence-transformation planner.

A previous independently reviewed stage has already selected the complete raw governed evidence relevant to one information need. The supplied transformation candidates consist only of those selected paths and bounded descendants of selected container paths.

Choose one generic operation and only the candidate input paths required by that operation. Do not calculate or return the operational answer yourself.

identity:
Use exactly one candidate path when that value already represents the requested information and needs no arithmetic, aggregation, or unit conversion.

bytes_to_gib:
Use exactly one numeric candidate path when that value represents a byte count of the requested quantity and converting that same quantity to GiB makes it answer-ready.

sum_bytes_to_gib:
Use two or more numeric candidate paths when those values are components of one requested byte-count total. Deterministic code will sum the chosen values and convert the total to GiB.

unsupported:
Use no input paths when none of the offered generic operations can safely create the requested answer from the candidates.

Prefer the smallest sufficient input set. Ignore redundant alternative representations when one candidate or one coherent component set is sufficient. Never combine a total with its component values. Never invent a unit, infer a missing fact, combine unrelated measurements, choose a provider-specific rule, or return an operational value.

Return only the required structured object."""


_REVIEW_INSTRUCTIONS = """You are Jason's independent evidence-transformation reviewer.

The information need, previously approved raw evidence, bounded transformation candidates, proposed operation, and proposed input paths are fixed.

Approve only when the chosen input paths are a sufficient non-redundant subset of the offered candidates and the proposed generic operation would produce an answer-ready value for the exact information need without inventing facts or units.

identity is valid only when exactly one chosen value already represents the requested answer without arithmetic, aggregation, or unit conversion.

bytes_to_gib is valid only when exactly one chosen numeric value is a byte count of the requested quantity.

sum_bytes_to_gib is valid only when every chosen numeric value is a byte-count component of the same requested total. Do not approve a mixture of an overall total and its individual components.

unsupported is justified only when none of the allowlisted operations can safely produce the requested answer from the offered candidates.

Do not calculate the result, repair the proposal, add paths, or return an operational value. Return only the required structured object."""


@dataclass(frozen=True, slots=True)
class ValidatedConversationEvidenceTransformer:
    """Plan semantically, review independently, execute deterministically."""

    planning: ValidatedReasoningPool
    reviewing: ValidatedReasoningPool

    def transform(
        self,
        *,
        question: str,
        evidence: Sequence[TransformEvidence],
    ) -> ConversationEvidenceTransformResult | None:
        clean_question = question.strip()

        if not clean_question:
            raise ValueError(
                "evidence transformation question is required"
            )

        selected = tuple(evidence)

        if not selected:
            raise ValueError(
                "evidence transformation requires selected evidence"
            )

        candidates = _candidate_evidence(selected)

        if not candidates:
            return None

        payload = {
            "information_need": clean_question,
            "allowed_operations": list(_ALLOWED_OPERATIONS),
            "selected_raw_evidence": [
                {
                    "path": item.path,
                    "value": _model_value(item.value),
                }
                for item in selected
            ],
            "transformation_candidates": [
                {
                    "path": item.path,
                    "value": _model_value(item.value),
                }
                for item in candidates
            ],
        }

        plan, _ = self.planning.complete_validated(
            system=_TRANSFORM_INSTRUCTIONS,
            user=json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_plan_schema(),
            max_output_tokens=192,
            validator=lambda proposal: self._validate_and_review(
                proposal=proposal,
                question=clean_question,
                selected=selected,
                candidates=candidates,
            ),
        )

        if plan.operation == "unsupported":
            return None

        candidate_by_path = {
            item.path: item
            for item in candidates
        }

        chosen = tuple(
            candidate_by_path[path]
            for path in plan.input_paths
        )

        return _apply_transform(
            plan=plan,
            chosen=chosen,
        )

    def _validate_and_review(
        self,
        *,
        proposal: Mapping[str, Any],
        question: str,
        selected: tuple[TransformEvidence, ...],
        candidates: tuple[TransformEvidence, ...],
    ) -> EvidenceTransformPlan:
        plan = _validate_plan(
            proposal=proposal,
            candidates=candidates,
        )

        candidate_by_path = {
            item.path: item
            for item in candidates
        }

        chosen = tuple(
            candidate_by_path[path]
            for path in plan.input_paths
        )

        review, _ = self.reviewing.complete_validated(
            system=_REVIEW_INSTRUCTIONS,
            user=json.dumps(
                {
                    "information_need": question,
                    "selected_raw_evidence": [
                        {
                            "path": item.path,
                            "value": _model_value(item.value),
                        }
                        for item in selected
                    ],
                    "proposed_operation": plan.operation,
                    "proposed_inputs": [
                        {
                            "path": item.path,
                            "value": _model_value(item.value),
                        }
                        for item in chosen
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            schema=_review_schema(),
            max_output_tokens=160,
            validator=_validate_review,
        )

        if not review.approved:
            if review.unsupported_is_justified:
                return EvidenceTransformPlan(
                    operation="unsupported",
                    input_paths=(),
                )

            raise ConversationEvidenceTransformError(
                "evidence transformation did not pass independent review"
            )

        if plan.operation == "unsupported":
            if (
                not review.unsupported_is_justified
                or review.unsupported_claim_risk
            ):
                raise ConversationEvidenceTransformError(
                    "unsupported transformation decision failed review"
                )

            return plan

        if (
            not review.operation_matches_evidence
            or not review.produces_answer_ready_value
            or review.unsupported_is_justified
            or review.unsupported_claim_risk
        ):
            raise ConversationEvidenceTransformError(
                "evidence transformation failed review dimensions"
            )

        return plan


def _plan_schema() -> Mapping[str, Any]:
    # Candidate paths are deliberately not embedded as enum values.
    # Provider data may contain arbitrary keys. Deterministic validation
    # below remains the authority for allowed input paths.
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "operation",
            "input_paths",
        ],
        "properties": {
            "operation": {
                "type": "string",
                "enum": list(_ALLOWED_OPERATIONS),
            },
            "input_paths": {
                "type": "array",
                "uniqueItems": True,
                "maxItems": _MAX_INPUT_PATHS,
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
            "operation_matches_evidence",
            "produces_answer_ready_value",
            "unsupported_is_justified",
            "unsupported_claim_risk",
        ],
        "properties": {
            "approved": {
                "type": "boolean",
            },
            "operation_matches_evidence": {
                "type": "boolean",
            },
            "produces_answer_ready_value": {
                "type": "boolean",
            },
            "unsupported_is_justified": {
                "type": "boolean",
            },
            "unsupported_claim_risk": {
                "type": "boolean",
            },
        },
    }


def _validate_plan(
    *,
    proposal: Mapping[str, Any],
    candidates: tuple[TransformEvidence, ...],
) -> EvidenceTransformPlan:
    if (
        not isinstance(proposal, Mapping)
        or set(proposal)
        != {
            "operation",
            "input_paths",
        }
    ):
        raise ConversationEvidenceTransformError(
            "evidence transformation plan shape is invalid"
        )

    operation = str(
        proposal.get(
            "operation",
            "",
        )
    ).strip().casefold()

    raw_paths = proposal.get(
        "input_paths",
        (),
    )

    if (
        not isinstance(raw_paths, Sequence)
        or isinstance(
            raw_paths,
            (str, bytes),
        )
    ):
        raise ConversationEvidenceTransformError(
            "evidence transformation input_paths must be an array"
        )

    input_paths = tuple(
        dict.fromkeys(
            str(item).strip()
            for item in raw_paths
            if str(item).strip()
        )
    )

    plan = EvidenceTransformPlan(
        operation=operation,
        input_paths=input_paths,
    )

    candidate_by_path = {
        item.path: item
        for item in candidates
    }

    if any(
        path not in candidate_by_path
        for path in input_paths
    ):
        raise ConversationEvidenceTransformError(
            "evidence transformation selected an unoffered input path"
        )

    if operation == "unsupported":
        if input_paths:
            raise ConversationEvidenceTransformError(
                "unsupported transformation cannot select input paths"
            )
        return plan

    if not input_paths:
        raise ConversationEvidenceTransformError(
            "supported transformation requires input paths"
        )

    chosen = tuple(
        candidate_by_path[path]
        for path in input_paths
    )

    if operation == "identity":
        if len(chosen) != 1:
            raise ConversationEvidenceTransformError(
                "identity transformation requires exactly one chosen input"
            )

    elif operation == "bytes_to_gib":
        if len(chosen) != 1:
            raise ConversationEvidenceTransformError(
                "bytes_to_gib requires exactly one chosen input"
            )

        _as_nonnegative_decimal(
            chosen[0].value
        )

    elif operation == "sum_bytes_to_gib":
        if len(chosen) < 2:
            raise ConversationEvidenceTransformError(
                "sum_bytes_to_gib requires at least two chosen inputs"
            )

        for item in chosen:
            _as_nonnegative_decimal(
                item.value
            )

    return plan


def _validate_review(
    proposal: Mapping[str, Any],
) -> EvidenceTransformReview:
    required = {
        "approved",
        "operation_matches_evidence",
        "produces_answer_ready_value",
        "unsupported_is_justified",
        "unsupported_claim_risk",
    }

    if (
        not isinstance(proposal, Mapping)
        or set(proposal) != required
    ):
        raise ConversationEvidenceTransformError(
            "evidence transformation review shape is invalid"
        )

    for key in required:
        if not isinstance(
            proposal.get(key),
            bool,
        ):
            raise ConversationEvidenceTransformError(
                "evidence transformation review booleans must be actual booleans"
            )

    return EvidenceTransformReview(
        approved=proposal["approved"],
        operation_matches_evidence=proposal[
            "operation_matches_evidence"
        ],
        produces_answer_ready_value=proposal[
            "produces_answer_ready_value"
        ],
        unsupported_is_justified=proposal[
            "unsupported_is_justified"
        ],
        unsupported_claim_risk=proposal[
            "unsupported_claim_risk"
        ],
    )


def _candidate_evidence(
    selected: tuple[TransformEvidence, ...],
) -> tuple[TransformEvidence, ...]:
    """Expose only selected roots and bounded descendants of those roots."""

    found: dict[str, TransformEvidence] = {}

    def walk(
        path: str,
        value: Any,
    ) -> None:
        if (
            len(found)
            >= _MAX_TRANSFORM_CANDIDATES
            and path not in found
        ):
            return

        if value == REDACTED:
            return

        if path not in found:
            found[path] = TransformEvidence(
                path=path,
                value=value,
            )

        if len(found) >= _MAX_TRANSFORM_CANDIDATES:
            return

        if isinstance(value, Mapping):
            for raw_key, child in value.items():
                child_path = _join_pointer(
                    path,
                    str(raw_key),
                )

                walk(
                    child_path,
                    child,
                )

                if len(found) >= _MAX_TRANSFORM_CANDIDATES:
                    break

        elif isinstance(
            value,
            (list, tuple),
        ):
            for index, child in enumerate(value):
                child_path = _join_pointer(
                    path,
                    str(index),
                )

                walk(
                    child_path,
                    child,
                )

                if len(found) >= _MAX_TRANSFORM_CANDIDATES:
                    break

    for item in selected:
        walk(
            item.path,
            item.value,
        )

        if len(found) >= _MAX_TRANSFORM_CANDIDATES:
            break

    return tuple(
        found.values()
    )


def _join_pointer(
    base: str,
    segment: str,
) -> str:
    escaped = (
        segment
        .replace("~", "~0")
        .replace("/", "~1")
    )

    if base == "/":
        return f"/{escaped}"

    return (
        f"{base.rstrip('/')}/{escaped}"
    )


def _model_value(
    value: Any,
) -> Any:
    if isinstance(value, Mapping):
        return {
            "type": "object",
            "keys": [
                str(key)
                for key in list(value.keys())[:32]
            ],
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return {
            "type": "array",
            "length": len(value),
        }

    if isinstance(value, str):
        normalized = " ".join(
            value.split()
        )

        if len(normalized) > _MAX_MODEL_STRING_CHARS:
            return (
                normalized[
                    :_MAX_MODEL_STRING_CHARS
                ]
                + "..."
            )

        return normalized

    return value


def _apply_transform(
    *,
    plan: EvidenceTransformPlan,
    chosen: tuple[TransformEvidence, ...],
) -> ConversationEvidenceTransformResult:
    if plan.operation == "identity":
        value = chosen[0].value

    elif plan.operation == "bytes_to_gib":
        value = _format_gib(
            _as_nonnegative_decimal(
                chosen[0].value
            )
        )

    elif plan.operation == "sum_bytes_to_gib":
        total = sum(
            (
                _as_nonnegative_decimal(
                    item.value
                )
                for item in chosen
            ),
            Decimal(0),
        )

        value = _format_gib(
            total
        )

    else:
        raise ConversationEvidenceTransformError(
            "unsupported transformation cannot be applied"
        )

    return ConversationEvidenceTransformResult(
        operation=plan.operation,
        value=value,
        source_paths=tuple(
            item.path
            for item in chosen
        ),
    )


def _as_nonnegative_decimal(
    value: Any,
) -> Decimal:
    if isinstance(value, bool):
        raise ConversationEvidenceTransformError(
            "boolean evidence is not a numeric measurement"
        )

    if not isinstance(
        value,
        (
            int,
            float,
            Decimal,
        ),
    ):
        raise ConversationEvidenceTransformError(
            "numeric transformation requires numeric evidence"
        )

    try:
        result = Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ConversationEvidenceTransformError(
            "numeric evidence is invalid"
        ) from exc

    if (
        not result.is_finite()
        or result < 0
    ):
        raise ConversationEvidenceTransformError(
            "numeric evidence must be finite and non-negative"
        )

    return result


def _format_gib(
    byte_count: Decimal,
) -> str:
    gib = (
        byte_count
        / _BYTES_PER_GIB
    )

    if gib == gib.to_integral_value():
        return f"{int(gib)} GiB"

    rounded = gib.quantize(
        Decimal("0.01")
    )

    return (
        f"{rounded.normalize()} GiB"
    )
