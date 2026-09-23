"""Turn governed provider evidence into answer-ready conversation support.

Evidence-location reasoning may inspect sanitized evidence, but it can select only
existing JSON Pointer paths. A separate optional generic transformation layer then
turns those verified raw inputs into one answer-ready support value.

No provider field mappings or question-specific fact rules live here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .conversation_answer import (
    ConversationSupport,
)
from .conversation_evidence_transform import (
    TransformEvidence,
    ValidatedConversationEvidenceTransformer,
)
from .conversation_kernel import (
    InformationNeed,
)
from .contracts import (
    OrchestrationResult,
    OrchestrationStatus,
)
from .dynamic_resource_response import (
    DynamicEvidenceReasoner,
)
from .evidence_reference import (
    resolve_evidence_pointer,
)
from .evidence_sanitization import (
    REDACTED,
    sanitize_evidence_tree,
)
from .canonical_fact_vocabulary import (
    DEFAULT_CANONICAL_FACT_VOCABULARY,
)
from .resource_evidence import (
    GovernedResourceEvidenceInterpreter,
)
from .semantic_fact_resolver import (
    DEFAULT_SEMANTIC_FACT_RESOLVER,
)


@dataclass(frozen=True, slots=True)
class ConversationEvidenceAssessment:
    """Whether governed evidence supports one information need."""

    status: str
    supports: tuple[
        ConversationSupport,
        ...,
    ] = ()
    selected_paths: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            "supported",
            "unsupported",
            "failed",
        }:
            raise ValueError(
                "conversation evidence assessment status is invalid"
            )

        if self.status == "supported":
            if (
                not self.supports
                or not self.selected_paths
                or self.reason is not None
            ):
                raise ValueError(
                    "supported assessment requires support and selected paths"
                )

        elif (
            self.supports
            or self.selected_paths
            or not (
                self.reason or ""
            ).strip()
        ):
            raise ValueError(
                "non-supported assessment requires only a bounded reason"
            )


@dataclass(frozen=True, slots=True)
class ConversationEvidenceSupportExtractor:
    """Select, dereference, and optionally transform governed evidence."""

    reasoner: DynamicEvidenceReasoner
    transformer: (
        ValidatedConversationEvidenceTransformer
        | None
    ) = None

    def assess(
        self,
        *,
        need: InformationNeed,
        result: OrchestrationResult,
        support_prefix: str,
        requested_facts: tuple[str, ...] = (),
    ) -> ConversationEvidenceAssessment:
        prefix = support_prefix.strip()

        if not prefix:
            raise ValueError(
                "support_prefix is required"
            )

        basic = _validate_result(
            result
        )

        if basic is not None:
            return basic

        deterministic = _deterministic_semantic_assessment(
            need=need,
            requested_facts=requested_facts,
            results=(result,),
            support_prefix=prefix,
        )

        if deterministic is not None:
            return deterministic

        sanitized = sanitize_evidence_tree(
            result.output["data"]
        )

        # Preserve the historical single-result path contract for call sites
        # that do not use answer-ready transformations.
        if self.transformer is None:
            selection = self.reasoner.select(
                question=_selection_question(
                    need
                ),
                sanitized_data=sanitized,
            )

            if (
                selection.answer_type
                == "unavailable"
            ):
                return ConversationEvidenceAssessment(
                    status="unsupported",
                    reason=(
                        "the governed evidence did not establish "
                        "the requested information"
                    ),
                )

            supports: list[
                ConversationSupport
            ] = []

            for index, path in enumerate(
                selection.evidence_paths,
                start=1,
            ):
                value = resolve_evidence_pointer(
                    sanitized,
                    path,
                )

                if value == REDACTED:
                    raise PermissionError(
                        "redacted evidence cannot become conversation support"
                    )

                supports.append(
                    ConversationSupport(
                        support_id=(
                            f"{prefix}-{index}"
                        ),
                        information_need=(
                            need.need
                        ),
                        target_reference=(
                            need.target.reference
                        ),
                        value=value,
                        evidence_reference=(
                            f"{result.execution_id}:{path}"
                        ),
                    )
                )

            return ConversationEvidenceAssessment(
                status="supported",
                supports=tuple(supports),
                selected_paths=(
                    selection.evidence_paths
                ),
            )

        return self.assess_many(
            need=need,
            results=(result,),
            support_prefix=prefix,
            requested_facts=requested_facts,
        )

    def assess_many(
        self,
        *,
        need: InformationNeed,
        results: tuple[
            OrchestrationResult,
            ...,
        ],
        support_prefix: str,
        requested_facts: tuple[str, ...] = (),
    ) -> ConversationEvidenceAssessment:
        prefix = support_prefix.strip()

        if not prefix:
            raise ValueError(
                "support_prefix is required"
            )

        if not results:
            raise ValueError(
                "cumulative evidence requires at least one result"
            )

        successful: list[
            OrchestrationResult
        ] = []

        sources: list[
            dict[str, object]
        ] = []

        for result in results:
            if (
                result.status
                is not OrchestrationStatus.SUCCEEDED
            ):
                continue

            provider = str(
                result.output.get(
                    "provider",
                    "",
                )
            ).strip()

            if (
                not provider
                or not result.provider_id
                or provider
                != result.provider_id
            ):
                raise RuntimeError(
                    "resource result provider provenance is missing or inconsistent"
                )

            if "data" not in result.output:
                raise RuntimeError(
                    "resource result does not contain governed provider data"
                )

            successful.append(result)

            sources.append(
                {
                    "data": sanitize_evidence_tree(
                        result.output["data"]
                    )
                }
            )

        if not successful:
            return ConversationEvidenceAssessment(
                status="failed",
                reason=(
                    "the governed resource reads did not complete successfully"
                ),
            )

        deterministic = _deterministic_semantic_assessment(
            need=need,
            requested_facts=requested_facts,
            results=tuple(successful),
            support_prefix=prefix,
        )

        if deterministic is not None:
            return deterministic

        sanitized = {
            "sources": sources
        }

        selection = self.reasoner.select(
            question=_selection_question(
                need
            ),
            sanitized_data=sanitized,
        )

        if (
            selection.answer_type
            == "unavailable"
        ):
            return ConversationEvidenceAssessment(
                status="unsupported",
                reason=(
                    "the accumulated governed evidence did not establish "
                    "the requested information"
                ),
            )

        selected: list[
            TransformEvidence
        ] = []

        for path in (
            selection.evidence_paths
        ):
            value = resolve_evidence_pointer(
                sanitized,
                path,
            )

            if value == REDACTED:
                raise PermissionError(
                    "redacted evidence cannot become conversation support"
                )

            selected.append(
                TransformEvidence(
                    path=path,
                    value=value,
                )
            )

        if self.transformer is not None:
            transformed = (
                self.transformer.transform(
                    question=_selection_question(
                        need
                    ),
                    evidence=tuple(selected),
                )
            )

            if transformed is None:
                return ConversationEvidenceAssessment(
                    status="unsupported",
                    reason=(
                        "the selected governed evidence could not be "
                        "safely transformed into the requested information"
                    ),
                )

            references = tuple(
                _source_evidence_reference(
                    path=path,
                    successful=tuple(
                        successful
                    ),
                )
                for path in (
                    transformed.source_paths
                )
            )

            return ConversationEvidenceAssessment(
                status="supported",
                supports=(
                    ConversationSupport(
                        support_id=(
                            f"{prefix}-1"
                        ),
                        information_need=(
                            need.need
                        ),
                        target_reference=(
                            need.target.reference
                        ),
                        value=(
                            transformed.value
                        ),
                        evidence_reference=(
                            "|".join(references)
                        ),
                    ),
                ),
                selected_paths=(
                    selection.evidence_paths
                ),
            )

        supports: list[
            ConversationSupport
        ] = []

        for index, item in enumerate(
            selected,
            start=1,
        ):
            supports.append(
                ConversationSupport(
                    support_id=(
                        f"{prefix}-{index}"
                    ),
                    information_need=(
                        need.need
                    ),
                    target_reference=(
                        need.target.reference
                    ),
                    value=item.value,
                    evidence_reference=(
                        _source_evidence_reference(
                            path=item.path,
                            successful=tuple(
                                successful
                            ),
                        )
                    ),
                )
            )

        return ConversationEvidenceAssessment(
            status="supported",
            supports=tuple(supports),
            selected_paths=(
                selection.evidence_paths
            ),
        )


def _validate_result(
    result: OrchestrationResult,
) -> ConversationEvidenceAssessment | None:
    if (
        result.status
        is not OrchestrationStatus.SUCCEEDED
    ):
        return ConversationEvidenceAssessment(
            status="failed",
            reason=(
                "the governed resource read did not complete successfully"
            ),
        )

    provider = str(
        result.output.get(
            "provider",
            "",
        )
    ).strip()

    if (
        not provider
        or not result.provider_id
        or provider != result.provider_id
    ):
        raise RuntimeError(
            "resource result provider provenance is missing or inconsistent"
        )

    if "data" not in result.output:
        raise RuntimeError(
            "resource result does not contain governed provider data"
        )

    return None


def _source_evidence_reference(
    *,
    path: str,
    successful: tuple[
        OrchestrationResult,
        ...,
    ],
) -> str:
    source_index, provider_path = (
        _cumulative_source_reference(
            path
        )
    )

    if source_index >= len(successful):
        raise RuntimeError(
            "evidence selection referenced an unknown governed source"
        )

    return (
        f"{successful[source_index].execution_id}:"
        f"{provider_path}"
    )


def _cumulative_source_reference(
    path: str,
) -> tuple[int, str]:
    """Map /sources/N/data/... to the originating governed result."""

    parts = path.split("/")

    if (
        len(parts) < 4
        or parts[0] != ""
        or parts[1] != "sources"
        or parts[3] != "data"
    ):
        raise RuntimeError(
            "cumulative evidence selection did not reference source data"
        )

    try:
        source_index = int(
            parts[2]
        )
    except ValueError as exc:
        raise RuntimeError(
            "cumulative evidence selection used an invalid source index"
        ) from exc

    if source_index < 0:
        raise RuntimeError(
            "cumulative evidence selection used an invalid source index"
        )

    provider_path = (
        "/"
        + "/".join(
            parts[4:]
        )
        if len(parts) > 4
        else "/"
    )

    return (
        source_index,
        provider_path,
    )


def _selection_question(
    need: InformationNeed,
) -> str:
    parts = [
        need.need.strip()
    ]

    if (
        need.temporal_scope
        != "unspecified"
    ):
        parts.append(
            f"temporal scope: {need.temporal_scope}"
        )

    if need.relationship is not None:
        parts.append(
            f"relationship: {need.relationship}"
        )

    return "; ".join(parts)



class _NoSemanticFallbackReasoner:
    """Prohibit language reasoning inside the deterministic semantic fast path."""

    def locate(
        self,
        *,
        requested_facts,
        data,
    ):
        return ()


def _deterministic_semantic_assessment(
    *,
    need: InformationNeed,
    requested_facts: tuple[str, ...],
    results: tuple[OrchestrationResult, ...],
    support_prefix: str,
) -> ConversationEvidenceAssessment | None:
    """Use already-governed answer-ready canonical evidence before model selection.

    Provider adapters and approved semantic mappings may project actual provider
    values beneath provider_data/semantic_evidence. GovernedResourceEvidenceInterpreter
    already validates that trust boundary deterministically.

    Boolean and descriptive-string facts may short-circuit Conversation
    Experience evidence reasoning here because they are already answer-ready.
    Other shapes continue through the existing selector/transformer path so
    capacity, collections, aggregation, arithmetic, and formatting behavior
    remain unchanged.
    """

    canonical = tuple(
        str(item).strip()
        for item in requested_facts
        if str(item).strip()
    )

    # Compatibility for non-progressive callers only. The normal Conversation
    # Experience path supplies the canonical obligation already established by
    # governed planning and does not reinterpret the human sentence here.
    if not canonical:
        canonical = (
            DEFAULT_SEMANTIC_FACT_RESOLVER
            .canonicalize_requested_facts(
                human_text=need.need,
                requested_facts=(need.need,),
            )
        )

    if len(canonical) != 1:
        return None

    resolution = DEFAULT_SEMANTIC_FACT_RESOLVER.resolve(
        canonical[0]
    )

    if (
        resolution is None
        or resolution.expected_shape
        not in {
            "boolean",
            "descriptive_string",
        }
    ):
        return None

    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=_NoSemanticFallbackReasoner(),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )

    verified = []

    for result in results:
        if result.status is not OrchestrationStatus.SUCCEEDED:
            continue

        try:
            facts = interpreter.interpret(
                result=result,
                requested_facts=(
                    resolution.canonical_fact,
                ),
                evidence_contexts={
                    resolution.canonical_fact: (
                        resolution.evidence_contexts
                    ),
                },
            )
        except LookupError:
            continue

        if len(facts) != 1:
            continue

        verified.append(
            (
                result,
                facts[0],
            )
        )

    if not verified:
        return None

    first_result, first_fact = verified[0]

    # Exact duplicate canonical observations are corroboration. Any conflicting
    # canonical values must not be silently collapsed into one assertion.
    for _, fact in verified[1:]:
        if (
            type(fact.value) is not type(first_fact.value)
            or fact.value != first_fact.value
        ):
            return None

    if (
        resolution.expected_shape == "boolean"
        and not isinstance(first_fact.value, bool)
    ):
        return None

    if (
        resolution.expected_shape == "descriptive_string"
        and (
            not isinstance(first_fact.value, str)
            or not first_fact.value.strip()
        )
    ):
        return None

    support_id = f"{support_prefix}-1"

    return ConversationEvidenceAssessment(
        status="supported",
        supports=(
            ConversationSupport(
                support_id=support_id,
                information_need=need.need,
                target_reference=need.target.reference,
                value=first_fact.value,
                evidence_reference=(
                    f"{first_result.execution_id}:"
                    f"{first_fact.json_pointer}"
                ),
            ),
        ),
        selected_paths=(
            first_fact.json_pointer,
        ),
    )
