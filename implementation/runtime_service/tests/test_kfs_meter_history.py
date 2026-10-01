from types import SimpleNamespace

import pytest

from jason_runtime.kfs_meter_history import (
    GovernedKfsMeterHistoryInvoker,
    ensure_meter_history_read_authority,
    resolve_period,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.print_capability_catalog import (
    KYOCERA_KFS_PROVIDER,
    PRINT_METER_HISTORY_SEARCH,
    PRINT_METER_USAGE_READ,
)


class FakeGrantRepository:
    def __init__(self):
        self.values = {}

    def get(self, grant_id):
        return self.values.get(grant_id)

    def put(self, grant):
        self.values[grant.grant_id] = grant


class FakeAuthority:
    def __init__(self):
        self.grants = FakeGrantRepository()


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


def test_meter_history_authority_seeds_exact_aot_observe_grants():
    authority = FakeAuthority()
    created = ensure_meter_history_read_authority(authority, enabled=True)

    assert created == (
        "production-kfs-read-print-meter-history-search",
        "production-kfs-read-print-meter-usage-read",
    )
    grants = list(authority.grants.values.values())
    assert {grant.capability for grant in grants} == {
        PRINT_METER_HISTORY_SEARCH,
        PRINT_METER_USAGE_READ,
    }
    assert all(grant.subject_id == "organization:aot" for grant in grants)
    assert all(grant.organization_id == "aot" for grant in grants)
    assert all(grant.client_id is None for grant in grants)
    assert all(grant.permission.value == "observe" for grant in grants)
    assert all(grant.approval_required is False for grant in grants)


def test_meter_history_authority_is_idempotent_and_disabled_by_default():
    authority = FakeAuthority()
    assert ensure_meter_history_read_authority(authority, enabled=False) == ()
    assert authority.grants.values == {}

    first = ensure_meter_history_read_authority(authority, enabled=True)
    second = ensure_meter_history_read_authority(authority, enabled=True)
    assert len(first) == 2
    assert second == ()


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
