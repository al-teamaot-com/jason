from datetime import datetime, timezone

import pytest

from orchestrator.provider_capability_readiness import (
    ProviderCapabilityReadiness,
    ReadinessReason,
    ReadinessState,
    evaluate_transition,
)
from orchestrator.provider_capability_readiness_store import (
    SQLiteProviderCapabilityReadinessStore,
)
from orchestrator.provider_readiness_alert import (
    project_readiness_alert,
)


NOW = datetime(
    2026,
    8,
    24,
    10,
    30,
    tzinfo=timezone.utc,
)


def readiness(
    *,
    state,
    reason,
    status=None,
):
    return ProviderCapabilityReadiness(
        provider_id="provider.example",
        capability_name="example.read",
        state=state,
        reason=reason,
        observed_at=NOW,
        evidence_source="probe-v1",
        provider_status_code=status,
    )


def test_first_unavailable_state_is_persisted_and_creates_one_alert(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        current = readiness(
            state=ReadinessState.UNAVAILABLE,
            reason=ReadinessReason.QUOTA_EXHAUSTED,
            status="429",
        )

        transition = evaluate_transition(
            previous=None,
            current=current,
        )

        alert = store.record(
            transition=transition
        )

        assert alert is not None

        saved = store.get(
            provider_id="provider.example",
            capability_name="example.read",
        )

        assert saved == current

        pending = store.pending_alerts()

        assert len(pending) == 1
        assert pending[0].reason is (
            ReadinessReason.QUOTA_EXHAUSTED
        )
        assert pending[0].provider_status_code == "429"

    finally:
        store.close()


def test_repeated_identical_failure_records_evidence_without_duplicate_alert(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        first = readiness(
            state=ReadinessState.UNAVAILABLE,
            reason=ReadinessReason.QUOTA_EXHAUSTED,
            status="429",
        )

        first_transition = evaluate_transition(
            previous=None,
            current=first,
        )

        store.record(
            transition=first_transition
        )

        second = readiness(
            state=ReadinessState.UNAVAILABLE,
            reason=ReadinessReason.QUOTA_EXHAUSTED,
            status="429",
        )

        second_transition = evaluate_transition(
            previous=store.get(
                provider_id="provider.example",
                capability_name="example.read",
            ),
            current=second,
        )

        second_alert = store.record(
            transition=second_transition
        )

        assert second_alert is None
        assert len(
            store.pending_alerts()
        ) == 1

        history = store.transition_history(
            provider_id="provider.example",
            capability_name="example.read",
        )

        assert len(history) == 2
        assert history[0]["changed"] == 1
        assert history[1]["changed"] == 0

    finally:
        store.close()


def test_recovery_creates_recovery_alert(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        failed = readiness(
            state=ReadinessState.UNAVAILABLE,
            reason=ReadinessReason.QUOTA_EXHAUSTED,
            status="429",
        )

        store.record(
            transition=evaluate_transition(
                previous=None,
                current=failed,
            )
        )

        recovered = readiness(
            state=ReadinessState.HEALTHY,
            reason=ReadinessReason.NONE,
        )

        alert = store.record(
            transition=evaluate_transition(
                previous=store.get(
                    provider_id="provider.example",
                    capability_name="example.read",
                ),
                current=recovered,
            )
        )

        assert alert is not None
        assert alert.event_kind == (
            "provider_capability_recovered"
        )

        pending = store.pending_alerts()

        assert len(pending) == 2

    finally:
        store.close()


def test_alert_delivery_is_explicit_and_idempotency_is_enforced(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        failed = readiness(
            state=ReadinessState.UNAVAILABLE,
            reason=ReadinessReason.PROVIDER_UNAVAILABLE,
        )

        alert = store.record(
            transition=evaluate_transition(
                previous=None,
                current=failed,
            )
        )

        assert alert is not None

        store.mark_alert_delivered(
            alert_event_id=alert.alert_event_id
        )

        assert store.pending_alerts() == ()

        with pytest.raises(
            KeyError,
            match="pending readiness alert",
        ):
            store.mark_alert_delivered(
                alert_event_id=alert.alert_event_id
            )

    finally:
        store.close()


def test_alert_projection_distinguishes_jason_runtime_from_provider_state(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        failed = readiness(
            state=ReadinessState.UNAVAILABLE,
            reason=ReadinessReason.QUOTA_EXHAUSTED,
            status="429",
        )

        alert = store.record(
            transition=evaluate_transition(
                previous=None,
                current=failed,
            )
        )

        projection = project_readiness_alert(
            event=alert,
            runtime_state="healthy",
        )

        assert projection.title == (
            "Provider capability unavailable"
        )

        assert projection.details[
            "jason_runtime_state"
        ] == "HEALTHY"

        assert projection.details[
            "provider_readiness_state"
        ] == "UNAVAILABLE"

        assert projection.details[
            "reason"
        ] == "quota_exhausted"

        assert projection.details[
            "provider_status_code"
        ] == "429"

    finally:
        store.close()
