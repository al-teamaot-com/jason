"""Turn governed orchestration evidence into bounded conversational support items.

The evidence selector may reason about sanitized data, but it can select only existing
JSON Pointer paths. Jason deterministically dereferences the selected values. This layer
never renders the answer and never treats an unsupported selection as a factual claim.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conversation_answer import ConversationSupport
from .conversation_kernel import InformationNeed
from .contracts import OrchestrationResult, OrchestrationStatus
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

        sanitized = sanitize_evidence_tree(result.output["data"])
        selection = self.reasoner.select(
            question=_selection_question(need),
            sanitized_data=sanitized,
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
            supports.append(
                ConversationSupport(
                    support_id=f"{prefix}-{index}",
                    information_need=need.need,
                    target_reference=need.target.reference,
                    value=value,
                    evidence_reference=f"{result.execution_id}:{path}",
                )
            )

        return ConversationEvidenceAssessment(
            status="supported",
            supports=tuple(supports),
            selected_paths=selection.evidence_paths,
        )


def _selection_question(need: InformationNeed) -> str:
    parts = [need.need.strip()]
    if need.temporal_scope != "unspecified":
        parts.append(f"temporal scope: {need.temporal_scope}")
    if need.relationship is not None:
        parts.append(f"relationship: {need.relationship}")
    return "; ".join(parts)
