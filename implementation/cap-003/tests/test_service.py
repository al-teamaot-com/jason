from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from jason_cap_003.context import AutotaskBusinessContext
from jason_cap_003.local_llm import BusinessContextBriefing
from jason_cap_003.service import AutotaskBusinessContextInvoker
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult
from orchestrator import OrchestrationMode, OrchestrationRequest


class FakeReader:
    def read_company_context(self, **kwargs):
        assert kwargs["company_name"] == "Atlantic Office Technologies"
        return AutotaskBusinessContext(
            company={"id": 208, "companyName": "Atlantic Office Technologies"},
            contacts=({"id": 1, "companyID": 208},),
            configurations=({"id": 2, "companyID": 208},),
            tickets=({"id": 3, "companyID": 208, "ticketNumber": "T1"},),
            contracts=(),
            projects=(),
        )


class FakeAnalyzer:
    def analyze(self, context):
        assert context.company_id == "208"
        return BusinessContextBriefing(
            model="qwen3:1.7b",
            executive_summary="Operational context summary.",
            operational_observations=("One recent ticket is present.",),
            service_risks=("Review unresolved work.",),
            recommended_focus=("Validate current priorities.",),
            notable_relationships=("Ticket and configuration share company 208.",),
            confidence="medium",
        )


def _request(tmp_path: Path) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-cap003-service",
        correlation_id="corr-cap003-service",
        principal_id="operator-al",
        organization_id="aot",
        capability_name="autotask.business.context",
        capability_version=None,
        requested_mode="local_ai",
        orchestration_mode=OrchestrationMode.EXECUTE,
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


def test_invoker_persists_derived_briefing_and_redacted_evidence(tmp_path) -> None:
    invoker = AutotaskBusinessContextInvoker(
        reader=FakeReader(),
        analyzer=FakeAnalyzer(),
        repository_root=tmp_path / "repository",
    )
    resolution = type(
        "Resolution",
        (),
        {"capability_name": "autotask.business.context"},
    )()

    result = invoker.invoke(
        request=_request(tmp_path),
        resolution=resolution,
    )

    assert result.output["company_id"] == "208"
    assert result.output["record_counts"] == {
        "contacts": 1,
        "configurations": 1,
        "tickets": 1,
        "contracts": 0,
        "projects": 0,
    }
    assert result.output["provider_side_change"] is False
    assert len(result.artifact_references) == 2

    evidence_path = tmp_path / "evidence" / "autotask-business-context-exec-cap003-service.json"
    text = evidence_path.read_text(encoding="utf-8")
    assert '"raw_provider_content_persisted": false' in text
    assert '"discovered_company_id": "208"' in text
    assert "ticketNumber" not in text
