from __future__ import annotations

from decimal import Decimal

from connectors.core.contracts import ConnectorResult
from jason_cap_002.runtime import CAPABILITY_NAME, build_ticket_intelligence_runtime
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator import OrchestrationMode, OrchestrationRequest, OrchestrationStatus


class DenyConnector:
    provider_name = "autotask"
    capabilities = frozenset({"autotask.ticket.search"})

    def execute(self, request):
        raise AssertionError("Check-only contacted Autotask.")


def _request(tmp_path, *, mode: OrchestrationMode) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-cap002-test",
        correlation_id="corr-cap002-test",
        principal_id="operator-al",
        organization_id="aot",
        capability_name=CAPABILITY_NAME,
        capability_version=None,
        requested_mode="local_ai",
        orchestration_mode=mode,
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
            maximum_input_tokens=8192,
            maximum_output_tokens=2048,
            maximum_attempts=1,
        ),
        arguments={
            "ticket_number": "T1",
            "scope": "aot-internal-ticket-analysis",
            "allowed_scope": "aot-internal-ticket-analysis",
            "evidence_directory": str(tmp_path / "evidence"),
        },
        requester_kind="human",
        allow_pilot_capability=True,
        allow_pilot_provider=True,
    )


def test_check_only_resolves_local_provider_without_invocation(tmp_path) -> None:
    runtime = build_ticket_intelligence_runtime(
        autotask_connector=DenyConnector(),
        event_store_path=tmp_path / "events.sqlite3",
        repository_root=tmp_path / "repository",
    )
    try:
        result = runtime.orchestrator.execute(
            _request(tmp_path, mode=OrchestrationMode.CHECK_ONLY)
        )
        events = runtime.event_store.list_by_execution("exec-cap002-test")
    finally:
        runtime.close()

    assert result.status is OrchestrationStatus.VALIDATED
    assert result.provider_id == "jason.local-ticket-intelligence"
    assert result.attempts == 0
    assert [event.event_type for event in events] == [
        "orchestration.request.received",
        "orchestration.capability.resolved",
        "orchestration.check_only.validated",
    ]
    assert events[-1].payload["provider_invoked"] is False
