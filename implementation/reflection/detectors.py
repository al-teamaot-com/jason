from __future__ import annotations

from .contracts import (
    ImprovementCandidateDraft,
    ReflectionRecord,
    ReflectionSignalKind,
)


_MAX_BOUNDED_PAGES = 2
_MAX_PROVIDER_CALLS = 4
_MAX_FALLBACKS = 1


def detect_candidate_drafts(
    record: ReflectionRecord,
) -> tuple[ImprovementCandidateDraft, ...]:
    """Detect bounded generic improvement candidates from structured telemetry.

    These detectors do not change policy, code, provider access, or authority.
    They only create review candidates from deterministic execution facts.
    """

    record.validate()
    candidates: list[ImprovementCandidateDraft] = []

    if _broader_search_succeeded_after_exact_miss(record):
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.SEARCH_BROADENING_SUCCESS,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Bounded broader search succeeded after exact miss",
                proposal=(
                    "Evaluate a provider-neutral bounded search-resolution policy "
                    "that can progress from exact matching to a broader normalized "
                    "strategy while preserving ambiguity checks and fail-closed target selection."
                ),
                rationale=(
                    "The execution recorded an exact search with zero results followed "
                    "by a broader search strategy that returned one or more results."
                ),
            )
        )

    if (
        record.requested_result_scope in {"single", "bounded"}
        and record.pagination_count > _MAX_BOUNDED_PAGES
    ):
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.EXCESSIVE_PAGINATION,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Narrow request required excessive pagination",
                proposal=(
                    "Evaluate a provider-neutral filter-pushdown or narrower selector "
                    "strategy so bounded intents do not require broad historical retrieval."
                ),
                rationale=(
                    f"The execution used {record.pagination_count} pages for a "
                    f"{record.requested_result_scope} result scope."
                ),
            )
        )

    if record.provider_call_count > _MAX_PROVIDER_CALLS:
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.EXCESSIVE_PROVIDER_CALLS,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Execution used a high provider-call count",
                proposal=(
                    "Evaluate whether selector planning, provider-side filtering, "
                    "correlation reuse, or evidence minimization can reduce provider calls "
                    "without weakening evidence or authority controls."
                ),
                rationale=f"The execution recorded {record.provider_call_count} provider calls.",
            )
        )

    if record.fallback_count > _MAX_FALLBACKS:
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.REPEATED_FALLBACKS,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Execution required repeated fallbacks",
                proposal=(
                    "Review the generic capability-selection or selector strategy to "
                    "reduce repeated fallback paths while retaining fail-closed behavior."
                ),
                rationale=f"The execution recorded {record.fallback_count} fallbacks.",
            )
        )

    if record.user_correction_category:
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.USER_CORRECTION,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Explicit user correction requires governed review",
                proposal=(
                    "Evaluate the correction as a reusable provider-neutral improvement; "
                    "promote it only after regression testing and human approval."
                ),
                rationale=(
                    "An explicit user correction was recorded under category "
                    f"{record.user_correction_category!r}."
                ),
            )
        )

    for candidate in candidates:
        candidate.validate()
    return tuple(candidates)


def _broader_search_succeeded_after_exact_miss(record: ReflectionRecord) -> bool:
    if len(record.search_strategies) < 2:
        return False
    if record.search_strategies[0].strip().casefold() != "exact":
        return False
    if record.search_result_counts[0] != 0:
        return False
    return any(
        strategy.strip().casefold() != "exact" and count > 0
        for strategy, count in zip(
            record.search_strategies[1:],
            record.search_result_counts[1:],
        )
    )
