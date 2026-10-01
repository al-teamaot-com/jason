from types import SimpleNamespace

import pytest

from jason_runtime.kfs_meter_history import (
    GovernedKfsMeterHistoryInvoker,
    resolve_period,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.print_capability_catalog import (
    KYOCERA_KFS_PROVIDER,
    PRINT_METER_HISTORY_SEARCH,
    PRINT_METER_USAGE_READ,
)


class FakeStore:
    def search(self, *, arguments, start, end):
        return {
            "serial": arguments["serial_number"],
            "start": start.isoformat(),
            "end": end.isoformat(),
            "count": 2,
        }

    def usage(self, *, arguments, start, end):
        return {
            "device": {"serial_number": arguments["serial_number"]},
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "usage": {"total_impressions": 1234},
            "warnings": [],
        }


def request(capability, arguments, *, organization_id="aot", client_id=None, requester_kind="human"):
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="authorized-caller",
        organization_id=organization_id,
        client_id=client_id,
        capability_name=capability,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.CHECK_ONLY,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=SimpleNamespace(),
        budget=SimpleNamespace(),
        arguments=arguments,
        permission_mode="observe",
        requester_kind=requester_kind,
    )


def resolution(capability):
    return SimpleNamespace(
        selected_provider_id=KYOCERA_KFS_PROVIDER,
        capability_name=capability,
    )


def test_month_resolves_in_business_timezone():
    start, end = resolve_period({"month": "2026-09", "timezone": "America/New_York"})
    assert start.isoformat() == "2026-09-01T04:00:00+00:00"
    assert end.isoformat() == "2026-10-01T04:00:00+00:00"


def test_usage_is_callable_by_authorized_human():
    result = GovernedKfsMeterHistoryInvoker(FakeStore()).invoke(
        request=request(
            PRINT_METER_USAGE_READ,
            {"serial_number": "ABC123", "month": "2026-09"},
        ),
        resolution=resolution(PRINT_METER_USAGE_READ),
    )
    assert result.output["data"]["usage"]["total_impressions"] == 1234


def test_usage_is_callable_by_authorized_agent_jason():
    result = GovernedKfsMeterHistoryInvoker(FakeStore()).invoke(
        request=request(
            PRINT_METER_USAGE_READ,
            {"serial_number": "ABC123", "month": "2026-09"},
            requester_kind="agent",
        ),
        resolution=resolution(PRINT_METER_USAGE_READ),
    )
    assert result.output["data"]["device"]["serial_number"] == "ABC123"


def test_history_search_is_callable_on_demand():
    result = GovernedKfsMeterHistoryInvoker(FakeStore()).invoke(
        request=request(
            PRINT_METER_HISTORY_SEARCH,
            {
                "serial_number": "ABC123",
                "start": "2026-09-01T00:00:00-04:00",
                "end": "2026-10-01T00:00:00-04:00",
            },
        ),
        resolution=resolution(PRINT_METER_HISTORY_SEARCH),
    )
    assert result.output["data"]["count"] == 2


def test_client_scoped_access_stays_fail_closed_until_mapping_exists():
    invoker = GovernedKfsMeterHistoryInvoker(FakeStore())
    with pytest.raises(PermissionError, match="AOT-internal"):
        invoker.invoke(
            request=request(
                PRINT_METER_USAGE_READ,
                {"serial_number": "ABC123", "month": "2026-09"},
                client_id="client-1",
            ),
            resolution=resolution(PRINT_METER_USAGE_READ),
        )
