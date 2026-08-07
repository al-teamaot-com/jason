from __future__ import annotations

from decimal import Decimal

from jason_cap_003.runtime import CAPABILITY_NAME, build_autotask_business_context_runtime
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator import OrchestrationMode, OrchestrationRequest, OrchestrationStatus


class DenyConnector:
    provider_name = "autotask"
    capabilities = frozenset(
        {
            "autotask.company.search",
            "autotask.contact.search",
            "autotask.configuration_item.search",
            "autotask.ticket.search",
            "autotask.contract.search",
            "autotask.project.search",
        }
    )

    def execute(self, request):
        raise AssertionError("Check-only contacted Autotask.")


def _request(tmp_path) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-cap003-test",
        correlation_id="corr-cap003-test",
        principal_id="operator-al",
        organization_id="aot",
        capability_name=CAPABILITY_NAME,
        capability_version=None,
        requested_mode="local_ai",
        orchestration_mode=OrchestrationMode.CHECK_ONLY,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=True,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
            maximum_input_tokens=16384,
            maximum_output_tokens=2048,
            maximum_attempts=1,
        ),
        arguments={
            "company_name": "Atlantic Office Technologies",
            "evidence_directory": str(tmp_path / "evidence"),
        },
        requester_kind="human",
        allow_pilot_capability=True,
        allow_pilot_provider=True,
    )


def test_check_only_resolves_business_context_without_provider_calls(tmp_path) -> None:
    runtime = build_autotask_business_context_runtime(
        autotask_connector=DenyConnector(),
        event_store_path=tmp_path / "events.sqlite3",
        repository_root=tmp_path / "repository",
    )
    try:
        result = runtime.orchestrator.execute(_request(tmp_path))
        events = runtime.event_store.list_by_execution("exec-cap003-test")
    finally:
        runtime.close()

    assert result.status is OrchestrationStatus.VALIDATED
    assert result.provider_id == "jason.local-autotask-business-context"
    assert result.attempts == 0
    assert [event.event_type for event in events] == [
        "orchestration.request.received",
        "orchestration.capability.resolved",
        "orchestration.check_only.validated",
    ]
    assert events[-1].payload["provider_invoked"] is False
