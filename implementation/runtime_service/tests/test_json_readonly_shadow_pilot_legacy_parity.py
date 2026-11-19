"""Read-only classifier parity with the actual existing DRMM legacy verifier.

Both paths use the same provider fake and its exact response envelopes.
Legacy *writes* are never invoked: this compares only read-only outcomes.
"""
from datetime import timedelta
import json
from pathlib import Path

import pytest

from jason_runtime.daily_drmm_alert_reconciliation import (
    RecentAlertVerifierRegistry, _provider_timestamp,
)
from implementation.runtime_service.tests.test_json_playbook_readonly_preprod import (
    compose, execute, prep,
)
from tests.test_json_governed_shadow_integration import FakeGovernedObserve, NOW


EXPECTED = {
    "unsupported": ("unsupported", "unsupported_class"),
    "old": ("out_of_scope", "outside_window"),
    "offline": ("waiting", "waiting_offline"),
    "active": ("unhealthy", "active_detections"),
    "healthy": ("healthy", "healthy_observed"),
}


class LegacyReadView:
    def __init__(self, provider):
        self.provider = provider

    def execute(self, capability, arguments):
        return self.provider.execute(capability, arguments)


@pytest.mark.parametrize("case", sorted(EXPECTED))
def test_original_legacy_verifier_and_json_shadow_same_provider_fixture(tmp_path, case):
    legacy_provider = FakeGovernedObserve(case=case)
    current = legacy_provider.execute("management.alert.search", {"status": "open"})
    alerts = current["evidence"]["data"]["alerts"]
    assert len(alerts) == 1
    alert = alerts[0]
    at = _provider_timestamp(alert)
    assert at is not None
    if at < NOW - timedelta(hours=24):
        legacy_disposition = "out_of_scope"
    else:
        decision = RecentAlertVerifierRegistry(LegacyReadView(legacy_provider)).verify(alert)
        legacy_disposition = decision.outcome

    prep(tmp_path)
    json_runner, request_factory, orchestrator = compose(tmp_path, case=case)
    try:
        observed = execute(json_runner)
        assert observed.status == "completed_readonly"
        assert (legacy_disposition, observed.step_id) == EXPECTED[case]
        legacy_read_capabilities = [name for name, _ in legacy_provider.calls]
        json_read_capabilities = [req["capability_name"] for req in request_factory.calls]
        assert legacy_read_capabilities == json_read_capabilities
        assert not legacy_provider.mutations
        assert not orchestrator.provider.mutations
        assert all(entry["type"] not in {"document", "remediation"}
                   for entry in observed.history)
    finally:
        json_runner.state.close()
