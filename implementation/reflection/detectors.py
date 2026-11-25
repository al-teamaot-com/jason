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

    warnings = set(record.warning_codes)
    if "worker_unsupported_capability_present" in warnings:
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.WORKER_UNSUPPORTED_CAPABILITY,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Ticket worker observed unsupported work",
                proposal=(
                    "Review recurring unsupported ticket categories for a bounded "
                    "provider-neutral playbook candidate. Do not change production "
                    "authority until normal regression and human approval gates pass."
                ),
                rationale=(
                    "The autonomous ticket scan classified one or more current tickets "
                    "as unsupported by promoted capabilities."
                ),
            )
        )

    if "worker_governance_blocked_present" in warnings:
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.WORKER_GOVERNANCE_BLOCKER,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Ticket worker observed governance-blocked work",
                proposal=(
                    "Review repeated admission, identity, or promotion blockers and "
                    "propose a narrowly scoped fix without weakening existing controls."
                ),
                rationale=(
                    "The autonomous ticket scan classified one or more current tickets "
                    "as governance blocked."
                ),
            )
        )

    # Warning codes are normalized by the trusted event collector. The detector
    # deliberately does not ingest arbitrary exception text or secret-bearing logs.
    if "engineering_worker_stalled" in warnings:
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.ENGINEERING_STALLED,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Engineering work stopped progressing",
                proposal=(
                    "Review worker heartbeat, durable next action, dependency and retry "
                    "eligibility; improve existing TODO reconciliation instead of creating "
                    "a second scheduler. Preserve authorization and bounded retries."
                ),
                rationale="Trusted telemetry reported a stalled engineering work item.",
            )
        )

    if "engineering_ci_repeat_failure" in warnings:
        candidates.append(
            ImprovementCandidateDraft(
                signal_kind=ReflectionSignalKind.ENGINEERING_CI_REPEAT_FAILURE,
                capability_name=record.capability_name,
                provider_id=record.provider_id,
                title="Repeated engineering validation failure",
                proposal=(
                    "Investigate the recurring CI failure class and propose reusable "
                    "regression coverage or bounded worker correction without bypassing "
                    "protected checks, approval or release requirements."
                ),
                rationale="Trusted telemetry classified repeated engineering CI failure.",
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
