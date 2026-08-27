"""Turn governed orchestration evidence into bounded conversational support items.

The evidence selector may reason about sanitized data, but it can select only existing
JSON Pointer paths. Jason deterministically dereferences the selected values. This layer
never renders the answer and never treats an unsupported selection as a factual claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .conversation_answer import ConversationSupport
from .conversation_kernel import ConversationKernelError, InformationNeed
from .conversation_evidence_reasoning import ConversationEvidenceReasoningError
from .contracts import OrchestrationResult, OrchestrationStatus
from .conversation_resource_observation import (
    VerifiedConversationResourceObservation,
)
from .dynamic_resource_response import DynamicEvidenceReasoner
from .evidence_reference import resolve_evidence_pointer
from .evidence_sanitization import REDACTED, sanitize_evidence_tree


@dataclass(frozen=True, slots=True)
class ConversationEvidenceAssessment:
    """Whether one governed result supports one provider-independent information need."""

    status: str
    supports: tuple[ConversationSupport, ...] = ()
    selected_paths: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"supported", "unsupported", "failed"}:
            raise ValueError("conversation evidence assessment status is invalid")
        if self.status == "supported":
            if not self.supports or not self.selected_paths or self.reason is not None:
                raise ValueError("supported assessment requires support and selected paths")
        elif self.supports or self.selected_paths or not (self.reason or "").strip():
            raise ValueError("non-supported assessment requires only a bounded reason")


@dataclass(frozen=True, slots=True)
class ConversationEvidenceSupportExtractor:
    """Select and dereference only evidence that directly supports one information need."""

    reasoner: DynamicEvidenceReasoner

    def assess(
        self,
        *,
        need: InformationNeed,
        result: OrchestrationResult,
        support_prefix: str,
        reasoning_context: Mapping[str, str] | None = None,
        verified_target: VerifiedConversationResourceObservation | None = None,
    ) -> ConversationEvidenceAssessment:
        prefix = support_prefix.strip()
        if not prefix:
            raise ValueError("support_prefix is required")
        if result.status is not OrchestrationStatus.SUCCEEDED:
            return ConversationEvidenceAssessment(
                status="failed",
                reason="the governed resource read did not complete successfully",
            )

        provider = str(result.output.get("provider", "")).strip()
        if not provider or not result.provider_id or provider != result.provider_id:
            raise RuntimeError(
                "resource result provider provenance is missing or inconsistent"
            )
        if "data" not in result.output:
            raise RuntimeError("resource result does not contain governed provider data")

        raw_data = result.output["data"]
        evidence_data, evidence_prefix = _factual_evidence_scope(
            raw_data=raw_data,
            verified_target=verified_target,
        )
        sanitized = sanitize_evidence_tree(evidence_data)

        try:
            select_kwargs = {
                "question": _selection_question(need),
                "sanitized_data": sanitized,
            }

            if reasoning_context is not None:
                select_kwargs["reasoning_context"] = reasoning_context

            selection = self.reasoner.select(**select_kwargs)
        except (
            ConversationKernelError,
            ConversationEvidenceReasoningError,
        ):
            # A bounded reasoning pool that cannot prove support has not
            # established the requested fact. For read-only progressive
            # fulfillment this is conservatively equivalent to unsupported
            # evidence, allowing Jason to continue through other registered
            # governed evidence sources. Structural/provenance/security
            # failures remain fatal and are intentionally not caught here.
            return ConversationEvidenceAssessment(
                status="unsupported",
                reason=(
                    "the bounded evidence assessment could not establish "
                    "the requested information from this governed result"
                ),
            )

        if selection.answer_type == "unavailable":
            return ConversationEvidenceAssessment(
                status="unsupported",
                reason="the governed evidence did not establish the requested information",
            )

        supports: list[ConversationSupport] = []
        for index, path in enumerate(selection.evidence_paths, start=1):
            value = resolve_evidence_pointer(sanitized, path)
            if value == REDACTED:
                raise PermissionError("redacted evidence cannot become conversation support")
            original_path = _original_evidence_path(
                evidence_prefix=evidence_prefix,
                selected_path=path,
            )
            supports.append(
                ConversationSupport(
                    support_id=f"{prefix}-{index}",
                    information_need=need.need,
                    target_reference=need.target.reference,
                    value=value,
                    evidence_reference=(
                        f"{result.execution_id}:{original_path}"
                    ),
                )
            )

        return ConversationEvidenceAssessment(
            status="supported",
            supports=tuple(supports),
            selected_paths=selection.evidence_paths,
        )



def _factual_evidence_scope(
    *,
    raw_data: object,
    verified_target: VerifiedConversationResourceObservation | None,
) -> tuple[object, str]:
    """Return only factual evidence once durable target identity is verified.

    Resource-resolution metadata establishes *which* governed resource the
    result represents. It is not itself evidence for arbitrary facts about
    that resource. Once the caller supplies a verified target observation,
    semantic fact assessment is therefore bounded to provider_data.

    Without a verified target, the existing full governed result remains
    available so discovery-oriented evidence assessment is unchanged.
    """

    if verified_target is None:
        return raw_data, ""

    if not isinstance(raw_data, Mapping):
        raise RuntimeError(
            "verified-target result data must be a mapping"
        )

    expected_id = verified_target.entity.canonical_id.strip()
    if not expected_id:
        raise RuntimeError(
            "verified target lacks durable canonical identity"
        )

    resolved_id = str(
        raw_data.get("resolved_resource_id", "")
    ).strip()

    if not resolved_id or resolved_id != expected_id:
        raise RuntimeError(
            "verified target is inconsistent with governed result identity"
        )

    raw_matches = raw_data.get("resource_matches")
    if (
        not isinstance(raw_matches, (list, tuple))
        or len(raw_matches) != 1
        or not isinstance(raw_matches[0], Mapping)
    ):
        raise RuntimeError(
            "verified-target factual evidence lacks one corroborating match"
        )

    match_id = str(
        raw_matches[0].get("resource_id", "")
    ).strip()

    if not match_id or match_id != expected_id:
        raise RuntimeError(
            "verified-target factual evidence identity is inconsistent"
        )

    if "provider_data" not in raw_data:
        raise RuntimeError(
            "verified-target result does not contain factual provider data"
        )

    return raw_data["provider_data"], "/provider_data"


def _original_evidence_path(
    *,
    evidence_prefix: str,
    selected_path: str,
) -> str:
    prefix = evidence_prefix.strip()
    path = selected_path.strip()

    if not path.startswith("/"):
        raise RuntimeError(
            "selected evidence path is not a JSON Pointer"
        )

    if not prefix:
        return path

    if not prefix.startswith("/"):
        raise RuntimeError(
            "evidence scope prefix is not a JSON Pointer"
        )

    if path == "/":
        return prefix

    return prefix.rstrip("/") + path

def _selection_question(need: InformationNeed) -> str:
    parts = [need.need.strip()]
    if need.temporal_scope != "unspecified":
        parts.append(f"temporal scope: {need.temporal_scope}")
    if need.relationship is not None:
        parts.append(f"relationship: {need.relationship}")
    return "; ".join(parts)
