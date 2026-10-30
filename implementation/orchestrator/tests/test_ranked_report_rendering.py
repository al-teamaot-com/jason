from __future__ import annotations

import copy

import pytest

from orchestrator.contracts import ExecutionStage, OrchestrationResult, OrchestrationStatus
from orchestrator.resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    GovernedTeamsResourceResponseRenderer,
)
from orchestrator.teams_conversation_flow import ConversationIntent


class ForbiddenReasoner:
    def locate(self, **kwargs):
        raise AssertionError("ranked reports must not depend on a language model")


def renderer():
    return GovernedTeamsResourceResponseRenderer(
        GovernedResourceEvidenceInterpreter(ForbiddenReasoner())
    )


def ranked_data():
    return {
        "report_type": "ranked_monthly_usage",
        "schema_version": "1.0",
        "period_start": "2026-10-01T04:00:00+00:00",
        "period_end": "2026-10-30T18:39:37+00:00",
        "fleet_devices_reported": 435,
        "fleet_devices_in_inventory": 435,
        "eligible_devices": 432,
        "exception_count": 3,
        "coverage_verified": True,
        "complete": False,
        "top_devices": [
            {
                "customer": "Unknown (not mapped in KFS)",
                "customer_mapping_verified": False,
                "printer_id": "BO",
                "black_white_pages": 54634,
                "color_pages": 0,
                "total_pages": 54634,
                "latest_reading_at": "2026-10-30T16:00:02+00:00",
                "color_counter_status": "zero_verified_from_total_and_bw",
            },
            {
                "customer": "Oak Grove United Methodist Church",
                "customer_mapping_verified": True,
                "printer_id": "ID# 1357",
                "black_white_pages": 17180,
                "color_pages": 9445,
                "total_pages": 26625,
                "latest_reading_at": "2026-10-30T16:00:02+00:00",
                "color_counter_status": "measured",
            },
        ],
        "warnings": ["KFS customer assignments missing for 304 managed printers"],
    }


def ranked_result(data=None, *, provider_id="kyocera_kfs", provenance="kyocera_kfs"):
    return OrchestrationResult(
        execution_id="exec-1",
        correlation_id="corr-1",
        capability_name="print.fleet.usage.rank",
        status=OrchestrationStatus.SUCCEEDED,
        stage=ExecutionStage.COMPLETED,
        reason_codes=("capability_completed",),
        resolution=None,
        output={"provider": provenance, "data": ranked_data() if data is None else data},
        provider_id=provider_id,
    )


def ranked_intent(**kwargs):
    return ConversationIntent(
        capability_name="print.fleet.usage.rank",
        arguments={
            "month": "2026-10",
            "limit": "5",
            "timezone": "America/New_York",
            "requested_facts": ("monthly print volume ranking",),
            **kwargs,
        },
        permission_mode="observe",
    )


def test_real_shape_produces_monthly_usage_table_without_model_reasoning():
    answer = renderer().render(ranked_result(), ranked_intent())
    assert "Provisional top 2 printer volumes" in answer
    assert "| Rank | Customer | Printer ID | B&W pages | Color pages | Total pages" in answer
    assert "| 1 | Unknown (not mapped in KFS) | BO | 54,634 | 0* | 54,634 |" in answer
    assert "| 2 | Oak Grove United Methodist Church | ID# 1357 | 17,180 | 9,445 | 26,625 |" in answer
    assert "432 with valid meter totals; 3 meter exceptions" in answer
    assert "matching total and B&W readings" in answer
    assert "KFS customer assignments missing for 304" in answer
    assert "Source: kyocera_kfs (governed read-only)." in answer
    assert "Pending" not in answer
    assert "upload" not in answer.lower()


@pytest.mark.parametrize("change,expected", [
    (lambda d: d["top_devices"][0].update(total_pages=999), "do not reconcile"),
    (lambda d: d["top_devices"][0].update(black_white_pages=-1), "nonnegative integers"),
    (lambda d: d.update(exception_count=0), "inventory and result counts"),
    (lambda d: d.update(complete=True), "incomplete ranked usage"),
    (lambda d: d["top_devices"].reverse(), "not sorted descending"),
    (lambda d: d.update(period_start="2026-09-01T04:00:00+00:00"), "does not match"),
])
def test_report_validation_fails_closed_on_conflicts(change, expected):
    data = copy.deepcopy(ranked_data())
    change(data)
    with pytest.raises(ValueError, match=expected):
        renderer().render(ranked_result(data), ranked_intent())


def test_provenance_mismatch_fails_closed():
    with pytest.raises(RuntimeError, match="provenance"):
        renderer().render(ranked_result(provider_id="other"), ranked_intent())


def test_report_requires_read_permission():
    bad = ConversationIntent(
        capability_name="print.fleet.usage.rank",
        arguments=dict(ranked_intent().arguments),
        permission_mode="execute",
    )
    with pytest.raises(PermissionError, match="authorized read"):
        renderer().render(ranked_result(), bad)
