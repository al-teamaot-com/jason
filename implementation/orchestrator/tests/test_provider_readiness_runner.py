from datetime import datetime, timezone

from orchestrator.provider_capability_readiness import (
    ProviderCapabilityObservation,
    ReadinessDimension,
    ReadinessReason,
    ReadinessState,
)
from orchestrator.provider_capability_readiness_store import (
    SQLiteProviderCapabilityReadinessStore,
)
from orchestrator.provider_readiness_runner import (
    ProviderCapabilityReadinessRunner,
)


NOW = datetime(
    2026,
    8,
    24,
    18,
    0,
    tzinfo=timezone.utc,
)


class Probe:
    def __init__(
        self,
        *,
        reason=ReadinessReason.NONE,
    ):
        self.reason = reason

    def observe(
        self,
        *,
        provider_id,
        capability_name,
        component_healthy=True,
    ):
        healthy = ReadinessDimension(
            checked=True,
            healthy=True,
        )

        if self.reason is ReadinessReason.NONE:
            capability = healthy
        else:
            capability = ReadinessDimension(
                checked=True,
                healthy=False,
                reason=self.reason,
            )

        return ProviderCapabilityObservation(
            provider_id=provider_id,
            capability_name=capability_name,
            observed_at=NOW,
            component=healthy,
            reachability=healthy,
            authentication=healthy,
            capability=capability,
            evidence_source="test-probe",
            probe_version="1",
            provider_status_code=(
                "429"
                if self.reason
                is ReadinessReason.QUOTA_EXHAUSTED
                else "200"
            ),
        )


def test_runner_persists_first_failure_and_creates_alert(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        runner = ProviderCapabilityReadinessRunner(
            store=store
        )

        result = runner.run_once(
            probe=Probe(
                reason=ReadinessReason.QUOTA_EXHAUSTED
            ),
            provider_id="provider.example",
            capability_name="example.read",
        )

        assert result.current.state is (
            ReadinessState.UNAVAILABLE
        )

        assert result.current.reason is (
            ReadinessReason.QUOTA_EXHAUSTED
        )

        assert result.transition.should_alert is True
        assert result.alert_event is not None

    finally:
        store.close()


def test_runner_suppresses_duplicate_alerts_for_same_state(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        runner = ProviderCapabilityReadinessRunner(
            store=store
        )

        first = runner.run_once(
            probe=Probe(
                reason=ReadinessReason.QUOTA_EXHAUSTED
            ),
            provider_id="provider.example",
            capability_name="example.read",
        )

        second = runner.run_once(
            probe=Probe(
                reason=ReadinessReason.QUOTA_EXHAUSTED
            ),
            provider_id="provider.example",
            capability_name="example.read",
        )

        assert first.alert_event is not None
        assert second.alert_event is None
        assert second.transition.changed is False
        assert second.transition.should_alert is False

    finally:
        store.close()


def test_runner_generates_recovery_alert(
    tmp_path,
):
    store = SQLiteProviderCapabilityReadinessStore(
        tmp_path / "readiness.sqlite3"
    )

    try:
        runner = ProviderCapabilityReadinessRunner(
            store=store
        )

        runner.run_once(
            probe=Probe(
                reason=ReadinessReason.QUOTA_EXHAUSTED
            ),
            provider_id="provider.example",
            capability_name="example.read",
        )

        recovered = runner.run_once(
            probe=Probe(),
            provider_id="provider.example",
            capability_name="example.read",
        )

        assert recovered.current.state is (
            ReadinessState.HEALTHY
        )

        assert recovered.transition.recovery is True
        assert recovered.transition.should_alert is True
        assert recovered.alert_event is not None
        assert recovered.alert_event.event_kind == (
            "provider_capability_recovered"
        )

    finally:
        store.close()
