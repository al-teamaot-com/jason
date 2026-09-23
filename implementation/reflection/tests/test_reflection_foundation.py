from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator.event_store import OrchestrationEvent
from reflection import (
    CandidateActorKind,
    CandidateLifecycle,
    ReflectionRecord,
    ReflectionService,
    ReflectionSignalKind,
    SQLiteReflectionStore,
    detect_candidate_drafts,
    reflection_record_from_events,
)


def record(**changes) -> ReflectionRecord:
    values = {
        "record_id": "record-1",
        "execution_id": "exec-1",
        "correlation_id": "corr-1",
        "organization_id": "aot",
        "client_id": "client-1",
        "capability_name": "documentation.organization.search",
        "provider_id": "itglue",
        "outcome": "succeeded",
        "normalized_intent": "organization_search",
        "selector_strategy": "bounded_name_resolution",
        "requested_result_scope": "single",
        "result_count": 1,
        "candidate_count": 1,
        "provider_call_count": 2,
        "pagination_count": 1,
        "fallback_count": 1,
        "evidence_item_count": 1,
        "duration_ms": 50.0,
        "search_strategies": ("exact", "contains"),
        "search_result_counts": (0, 1),
        "warning_codes": (),
        "observed_at": datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc),
    }
    values.update(changes)
    return ReflectionRecord(**values)


def terminal_event(**payload_changes) -> OrchestrationEvent:
    payload = {
        "execution_id": "exec-1",
        "correlation_id": "corr-1",
        "organization_id": "aot",
        "client_id": "client-1",
        "principal_id": "person-al",
        "capability_name": "documentation.organization.search",
        "stage": "completed",
        "provider_id": "itglue",
        "status": "succeeded",
        "duration_ms": 50,
        "reflection_normalized_intent": "organization_search",
        "reflection_selector_strategy": "bounded_name_resolution",
        "reflection_requested_result_scope": "single",
        "reflection_result_count": 1,
        "reflection_candidate_count": 1,
        "reflection_provider_call_count": 2,
        "reflection_pagination_count": 1,
        "reflection_fallback_count": 1,
        "reflection_evidence_item_count": 1,
        "reflection_search_strategies": ("exact", "contains"),
        "reflection_search_result_counts": (0, 1),
        "reflection_warning_codes": (),
    }
    payload.update(payload_changes)
    return OrchestrationEvent(
        event_type="orchestration.capability.completed",
        execution_id="exec-1",
        correlation_id="corr-1",
        organization_id="aot",
        principal_id="person-al",
        capability_name="documentation.organization.search",
        stage="completed",
        payload=payload,
        occurred_at=datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc),
    )


def test_exact_miss_then_broader_success_creates_generic_candidate() -> None:
    candidates = detect_candidate_drafts(record())
    assert [item.signal_kind for item in candidates] == [
        ReflectionSignalKind.SEARCH_BROADENING_SUCCESS
    ]
    assert "Hitt" not in candidates[0].proposal
    assert "Autotask" not in candidates[0].proposal


def test_narrow_request_with_excessive_pagination_and_calls_creates_candidates() -> None:
    candidates = detect_candidate_drafts(
        record(
            search_strategies=(),
            search_result_counts=(),
            pagination_count=5,
            provider_call_count=7,
            fallback_count=0,
        )
    )
    assert {item.signal_kind for item in candidates} == {
        ReflectionSignalKind.EXCESSIVE_PAGINATION,
        ReflectionSignalKind.EXCESSIVE_PROVIDER_CALLS,
    }


def test_explicit_user_correction_is_signal_not_authority() -> None:
    candidates = detect_candidate_drafts(
        record(
            search_strategies=(),
            search_result_counts=(),
            user_correction_category="provider_filter_pushdown",
        )
    )
    assert [item.signal_kind for item in candidates] == [
        ReflectionSignalKind.USER_CORRECTION
    ]
    assert "human approval" in candidates[0].proposal


def test_store_is_append_only_and_scoped(tmp_path: Path) -> None:
    path = tmp_path / "reflection.sqlite3"
    store = SQLiteReflectionStore(path)
    try:
        item = record()
        store.append_record(item)
        with pytest.raises(ValueError, match="already exists"):
            store.append_record(item)

        assert store.get_record("record-1", organization_id="aot") == item
        assert store.get_record("record-1", organization_id="other") is None
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        store.close()


def test_repeated_signal_reuses_candidate_and_adds_source_evidence() -> None:
    store = SQLiteReflectionStore()
    service = ReflectionService(store)
    try:
        first = service.observe(record())
        second = service.observe(
            record(
                record_id="record-2",
                execution_id="exec-2",
                correlation_id="corr-2",
            )
        )
        assert len(first.candidates) == 1
        assert len(second.candidates) == 1
        assert first.candidates[0].candidate_key == second.candidates[0].candidate_key
        assert second.candidates[0].state is CandidateLifecycle.OBSERVED
        assert second.candidates[0].source_record_ids == ("record-1", "record-2")
    finally:
        store.close()


def test_candidate_cannot_skip_review_lifecycle() -> None:
    store = SQLiteReflectionStore()
    service = ReflectionService(store)
    try:
        observed = service.observe(record()).candidates[0]
        with pytest.raises(PermissionError, match="human governance actor"):
            store.transition_candidate(
                observed.candidate_key,
                organization_id="aot",
                new_state=CandidateLifecycle.APPROVED,
                actor_id="system:reflection-detector",
                actor_kind=CandidateActorKind.SYSTEM,
                reason="self approval attempt",
            )
        with pytest.raises(ValueError, match="invalid candidate transition"):
            store.transition_candidate(
                observed.candidate_key,
                organization_id="aot",
                new_state=CandidateLifecycle.APPROVED,
                actor_id="person-al",
                actor_kind=CandidateActorKind.HUMAN,
                reason="skip review",
            )

        proposed = store.transition_candidate(
            observed.candidate_key,
            organization_id="aot",
            new_state=CandidateLifecycle.PROPOSED,
            actor_id="person-al",
            actor_kind=CandidateActorKind.HUMAN,
            reason="review candidate",
        )
        assert proposed.state is CandidateLifecycle.PROPOSED
        tested = store.transition_candidate(
            observed.candidate_key,
            organization_id="aot",
            new_state=CandidateLifecycle.TESTED,
            actor_id="ci:reflection-regression",
            actor_kind=CandidateActorKind.CI,
            reason="regression cases passed",
        )
        approved = store.transition_candidate(
            observed.candidate_key,
            organization_id="aot",
            new_state=CandidateLifecycle.APPROVED,
            actor_id="person-al",
            actor_kind=CandidateActorKind.HUMAN,
            reason="governance approval",
        )
        promoted = store.transition_candidate(
            observed.candidate_key,
            organization_id="aot",
            new_state=CandidateLifecycle.PROMOTED,
            actor_id="release:controlled",
            actor_kind=CandidateActorKind.RELEASE,
            reason="merged reviewed implementation",
        )
        assert tested.state is CandidateLifecycle.TESTED
        assert approved.state is CandidateLifecycle.APPROVED
        assert promoted.state is CandidateLifecycle.PROMOTED
    finally:
        store.close()


def test_candidate_scope_cannot_cross_organization() -> None:
    store = SQLiteReflectionStore()
    service = ReflectionService(store)
    try:
        candidate = service.observe(record()).candidates[0]
        assert store.get_candidate(candidate.candidate_key, organization_id="other") is None
        with pytest.raises(ValueError, match="not found"):
            store.transition_candidate(
                candidate.candidate_key,
                organization_id="other",
                new_state=CandidateLifecycle.PROPOSED,
                actor_id="person-x",
                actor_kind=CandidateActorKind.HUMAN,
                reason="cross-org attempt",
            )
    finally:
        store.close()


def test_collector_uses_bounded_terminal_telemetry_only() -> None:
    item = reflection_record_from_events([terminal_event()], record_id="record-1")
    assert item.organization_id == "aot"
    assert item.provider_call_count == 2
    assert item.search_strategies == ("exact", "contains")
    assert item.search_result_counts == (0, 1)


def test_collector_rejects_mixed_execution_timelines() -> None:
    other = OrchestrationEvent(
        event_type="orchestration.capability.completed",
        execution_id="exec-2",
        correlation_id="corr-2",
        organization_id="aot",
        principal_id="person-al",
        capability_name="documentation.organization.search",
        stage="completed",
        payload={
            "execution_id": "exec-2",
            "correlation_id": "corr-2",
            "organization_id": "aot",
            "principal_id": "person-al",
            "capability_name": "documentation.organization.search",
            "stage": "completed",
            "status": "succeeded",
        },
    )
    with pytest.raises(ValueError, match="one execution/correlation"):
        reflection_record_from_events([terminal_event(), other])


def test_record_rejects_unbounded_or_misaligned_search_telemetry() -> None:
    with pytest.raises(ValueError, match="must align"):
        record(search_strategies=("exact",), search_result_counts=()).validate()
    with pytest.raises(ValueError, match="unbounded"):
        record(
            search_strategies=tuple("contains" for _ in range(33)),
            search_result_counts=tuple(1 for _ in range(33)),
        ).validate()
