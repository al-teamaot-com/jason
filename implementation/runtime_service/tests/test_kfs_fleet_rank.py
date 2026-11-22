from types import SimpleNamespace

import pytest

from jason_runtime.kfs_fleet_rank import rank_fleet_usage
from jason_runtime.kfs_meter_history import GovernedKfsMeterHistoryInvoker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.print_capability_catalog import PRINT_FLEET_USAGE_RANK, KYOCERA_KFS_PROVIDER


def device(number, total, *, customer="AOT Client", verified=True):
    return {
        "device_id": f"dev-{number}",
        "management_status": 1,
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

def test_complete_list_preserves_every_inventoried_device_and_missing_boundary_row():
    records = [device(i, i * 10, customer="" if i % 3 == 0 else "Client") for i in range(435)]
    for index in (2, 55, 434):
        records[index] = device(index, 0, verified=False)
    result = rank_fleet_usage(source(records), report_mode="list")
    assert result["report_mode"] == "list"
    assert result["selected_device_count"] == 435
    assert result["returned_row_count"] == 435
    assert len(result["listed_devices"]) == 435
    assert len({row["device_id"] for row in result["listed_devices"]}) == 435
    assert result["usage_verified_count"] == 432
    assert result["usage_exception_count"] == 3
    assert len(result["ranked_devices"]) == 0
    failures = [x for x in result["listed_devices"] if x["usage_status"] == "exception"]
    assert len(failures) == 3
    assert all(x["total_impressions"] is None for x in failures)
    assert all(x["black_white_impressions"] is None for x in failures)
    assert all(x["color_impressions"] is None for x in failures)
    assert all(x["exception_reasons"] for x in failures)


def test_complete_list_never_guesses_unverified_customer_and_preserves_measured_zero():
    records = [device(1, 0, customer=""), device(2, 15, customer="Known")]
    result = rank_fleet_usage(source(records), report_mode="list")
    rows = result["listed_devices"]
    unknown = next(x for x in rows if x["serial_number"] == "SER0001")
    assert unknown["customer_name"] == ""
    assert unknown["customer_mapping_status"] == "not_found"
    assert unknown["total_impressions"] == 0
    assert unknown["usage_status"] == "verified"
    assert result["customer_mapping_missing_count"] == 1


def test_list_still_refuses_unverified_or_truncated_source():
    records = [device(i, i * 5) for i in range(100)]
    payload = source(records)
    payload["selected_device_count"] = 435
    with pytest.raises(ValueError, match="incomplete"):
        rank_fleet_usage(payload, report_mode="list")


def test_list_rejects_excessive_source_even_with_claimed_coverage():
    records = [device(i, i) for i in range(1001)]
    with pytest.raises(ValueError, match="incomplete"):
        rank_fleet_usage(source(records), report_mode="list")


def test_bad_report_mode_fails_closed():
    with pytest.raises(ValueError, match="report_mode"):
        rank_fleet_usage(source([device(1, 10)]), report_mode="export_and_bill")


def test_invoker_complete_list_uses_full_source_and_never_device_filter():
    store = Store()
    req = request()
    req.arguments["report_mode"] = "list"
    result = GovernedKfsMeterHistoryInvoker(store).invoke(
        request=req,
        resolution=SimpleNamespace(
            selected_provider_id=KYOCERA_KFS_PROVIDER,
            capability_name=PRINT_FLEET_USAGE_RANK,
        ),
    )
    assert result.output["data"]["returned_row_count"] == 2
    assert len(result.output["data"]["listed_devices"]) == 2
    assert "device_id" not in store.arguments
    assert store.arguments["limit"] == 1000

def test_managed_only_filters_unmanaged_from_435_before_billable_output():
    records = [device(i, i * 7) for i in range(435)]
    for index in range(20):
        records[index]["management_status"] = 0
    output = rank_fleet_usage(source(records), report_mode="list")
    assert output["full_inventory_device_count"] == 435
    assert output["selected_device_count"] == 415
    assert output["unmanaged_excluded_count"] == 20
    assert output["returned_row_count"] == 415
    assert output["usage_verified_count"] == 415
    assert not any(row["serial_number"] == "SER0000" for row in output["listed_devices"])
    assert len({row["device_id"] for row in output["listed_devices"]}) == 415


def test_unmanaged_can_be_included_only_when_explicitly_selected():
    records = [device(i, i * 4) for i in range(2)]
    records[0]["management_status"] = 0
    result = rank_fleet_usage(source(records), report_mode="list", managed_only=False)
    assert result["selected_device_count"] == 2
    assert result["unmanaged_excluded_count"] == 0
    assert result["listed_devices"][0]["management_status"] in (0, 1)


def test_unknown_management_status_fails_closed_for_managed_report():
    records = [device(1, 10)]
    records[0].pop("management_status")
    with pytest.raises(ValueError, match="management_status"):
        rank_fleet_usage(source(records), report_mode="list")


def test_invalid_managed_only_selector_does_not_silently_expand_fleet():
    with pytest.raises(ValueError, match="managed_only"):
        rank_fleet_usage(source([device(1, 10)]), managed_only="false")


def test_invoker_defaults_to_managed_only_for_fleet_reports():
    store = Store()
    result = GovernedKfsMeterHistoryInvoker(store).invoke(
        request=request(),
        resolution=SimpleNamespace(
            selected_provider_id=KYOCERA_KFS_PROVIDER,
            capability_name=PRINT_FLEET_USAGE_RANK,
        ),
    )
    assert result.output["data"]["managed_only"] is True
    assert result.output["data"]["unmanaged_excluded_count"] == 0
