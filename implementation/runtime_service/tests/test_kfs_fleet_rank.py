from types import SimpleNamespace

import pytest

from jason_runtime.kfs_fleet_rank import rank_fleet_usage
from jason_runtime.kfs_meter_history import GovernedKfsMeterHistoryInvoker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.print_capability_catalog import PRINT_FLEET_USAGE_RANK, KYOCERA_KFS_PROVIDER


def device(number, total, *, customer="AOT Client", verified=True):
    return {
        "device_id": f"dev-{number}",
        "serial_number": f"SER{number:04d}",
        "equipment_id": f"EQ-{number}",
        "customer_name": customer,
        "customer_mapping_status": "verified" if customer else "not_found",
        "usage_status": "verified" if verified else "exception",
        "total_impressions": total if verified else None,
        "black_white_impressions": total if verified else None,
        "color_impressions": 0 if verified else None,
        "warnings": [] if verified else ["missing boundary"],
        "boundary_start_at": "2026-10-01T04:00:00+00:00",
        "boundary_end_at": "2026-11-01T04:00:00+00:00",
        "inventory_run_id": "run-1",
    }


def source(records):
    return {
        "period_start": "2026-10-01T04:00:00+00:00",
        "period_end": "2026-11-01T04:00:00+00:00",
        "records": records,
        "selected_device_count": len(records),
        "fleet_devices_in_inventory": len(records),
        "fleet_devices_reported": len(records),
        "inventory_coverage_verified": True,
        "warnings": [],
    }


def test_complete_435_fleet_top_five_and_exceptions():
    records = [device(i, i * 10, customer="" if i % 3 == 0 else "Client") for i in range(435)]
    records[2] = device(2, 0, verified=False)
    result = rank_fleet_usage(source(records))
    assert result["inventory_coverage_verified"]
    assert result["selected_device_count"] == 435
    assert result["usage_verified_count"] == 434
    assert result["usage_exception_count"] == 1
    assert result["customer_mapping_missing_count"] == 145
    assert [x["serial_number"] for x in result["ranked_devices"]] == [
        "SER0434", "SER0433", "SER0432", "SER0431", "SER0430"
    ]


def test_ties_deterministic_and_unknown_customer_not_guessed():
    records = [device(2, 10, customer=""), device(1, 10, customer="Known")]
    result = rank_fleet_usage(source(records), metric="black_white", top_n=2)
    assert [x["serial_number"] for x in result["ranked_devices"]] == ["SER0001", "SER0002"]
    assert result["ranked_devices"][1]["customer_name"] == ""
    assert result["customer_mapping_missing_count"] == 1


@pytest.mark.parametrize("problem", ["coverage", "truncation", "duplicate", "missing"])
def test_incomplete_or_bad_fleet_refused(problem):
    records = [device(1, 9), device(2, 10)]
    payload = source(records)
    if problem == "coverage":
        payload["inventory_coverage_verified"] = False
    elif problem == "truncation":
        payload["warnings"] = ["Usage records were truncated by governed source limit"]
    elif problem == "duplicate":
        payload["records"][1]["device_id"] = "dev-1"
    else:
        payload["selected_device_count"] = 3
    with pytest.raises(ValueError):
        rank_fleet_usage(payload)


@pytest.mark.parametrize("metric,top_n", [("lifetime", 5), ("total", 0), ("color", 51), ("total", True)])
def test_bad_parameters_refused(metric, top_n):
    with pytest.raises(ValueError):
        rank_fleet_usage(source([device(1, 10)]), metric=metric, top_n=top_n)


class Store:
    def __init__(self):
        self.arguments = None

    def usage_search(self, *, arguments, start, end):
        self.arguments = dict(arguments)
        return source([device(1, 10), device(2, 20)])


def request(client_id=None):
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="authorized-caller",
        organization_id="aot",
        client_id=client_id,
        capability_name=PRINT_FLEET_USAGE_RANK,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.CHECK_ONLY,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=SimpleNamespace(),
        budget=SimpleNamespace(),
        arguments={"month": "2026-10", "top_n": 1, "limit": 1, "device_id": "dev-1"},
        permission_mode="observe",
        requester_kind="human",
    )


def test_invoker_ranks_full_source_without_client_side_first_page():
    store = Store()
    result = GovernedKfsMeterHistoryInvoker(store).invoke(
        request=request(),
        resolution=SimpleNamespace(selected_provider_id=KYOCERA_KFS_PROVIDER, capability_name=PRINT_FLEET_USAGE_RANK),
    )
    assert result.output["data"]["ranked_devices"][0]["serial_number"] == "SER0002"
    assert store.arguments["limit"] == 1000
    assert "device_id" not in store.arguments


def test_client_specific_invocation_denied_without_mapping():
    with pytest.raises(PermissionError, match="AOT-internal"):
        GovernedKfsMeterHistoryInvoker(Store()).invoke(
            request=request(client_id="client-123"),
            resolution=SimpleNamespace(selected_provider_id=KYOCERA_KFS_PROVIDER, capability_name=PRINT_FLEET_USAGE_RANK),
        )
