from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from jason_cap_003.context import AutotaskBusinessContext
from jason_cap_003.local_llm import BusinessContextBriefing
from jason_cap_003.service import AutotaskBusinessContextInvoker
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator import OrchestrationMode, OrchestrationRequest


class FakeReader:
    def read_company_context(self, **kwargs):
        assert kwargs["company_name"] == "Atlantic Office Technologies"
        focus_ticket_number = kwargs.get("focus_ticket_number")
        tickets = [
            {"id": 3, "companyID": 208, "ticketNumber": "T1", "title": "First"},
            {"id": 4, "companyID": 208, "ticketNumber": "T2", "title": "Second"},
        ]
        if focus_ticket_number == "T999":
            tickets.insert(
                0,
                {"id": 999, "companyID": 208, "ticketNumber": "T999", "title": "Focused"},
            )
        return AutotaskBusinessContext(
            company={"id": 208, "companyName": "Atlantic Office Technologies"},
            contacts=({"id": 1, "companyID": 208},),
            configurations=({"id": 2, "companyID": 208},),
            tickets=tuple(tickets),
            contracts=(),
            projects=(),
        )


class FakeAnalyzer:
    def __init__(self) -> None:
        self.focus_ticket_number = None

    def analyze(self, context, *, focus_ticket_number=None):
        assert context.company_id == "208"
        self.focus_ticket_number = focus_ticket_number
        return BusinessContextBriefing(
            model="qwen3:1.7b",
            executive_summary="Operational context summary.",
            operational_observations=("One recent ticket is present.",),
            service_risks=("Review unresolved work.",),
            recommended_focus=("Validate current priorities.",),
            notable_relationships=("Ticket and configuration share company 208.",),
            confidence="medium",
        )


def _request(tmp_path: Path, *, ticket_number: str | None = None) -> OrchestrationRequest:
    arguments = {
        "company_name": "Atlantic Office Technologies",
        "evidence_directory": str(tmp_path / "evidence"),
    }
    if ticket_number is not None:
        arguments["ticket_number"] = ticket_number
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
        arguments=arguments,
        requester_kind="human",
        allow_pilot_capability=True,
        allow_pilot_provider=True,
    )


def _resolution():
    return type(
        "Resolution",
        (),
        {"capability_name": "autotask.business.context"},
    )()


def test_invoker_persists_derived_briefing_and_redacted_evidence(tmp_path) -> None:
    analyzer = FakeAnalyzer()
    invoker = AutotaskBusinessContextInvoker(
        reader=FakeReader(),
        analyzer=analyzer,
        repository_root=tmp_path / "repository",
    )

    result = invoker.invoke(
        request=_request(tmp_path),
        resolution=_resolution(),
    )

    assert analyzer.focus_ticket_number is None
    assert result.output["company_id"] == "208"
    assert result.output["focused_ticket_number"] is None
    assert result.output["record_counts"] == {
        "contacts": 1,
        "configurations": 1,
        "tickets": 2,
        "contracts": 0,
        "projects": 0,
    }
    assert result.output["provider_side_change"] is False
    assert len(result.artifact_references) == 2

    evidence_path = tmp_path / "evidence" / "autotask-business-context-exec-cap003-service.json"
    text = evidence_path.read_text(encoding="utf-8")
    assert '"raw_provider_content_persisted": false' in text
    assert '"discovered_company_id": "208"' in text
    assert '"focused_ticket_number": null' in text
    assert "ticketNumber" not in text


def test_invoker_routes_ticket_focus_through_same_business_context_capability(tmp_path) -> None:
    analyzer = FakeAnalyzer()
    invoker = AutotaskBusinessContextInvoker(
        reader=FakeReader(),
        analyzer=analyzer,
        repository_root=tmp_path / "repository",
    )

    result = invoker.invoke(
        request=_request(tmp_path, ticket_number="T2"),
        resolution=_resolution(),
    )

    assert analyzer.focus_ticket_number == "T2"
    assert result.output["focused_ticket_number"] == "T2"
    assert result.output["company_id"] == "208"
    assert result.output["provider_side_change"] is False

    evidence_path = tmp_path / "evidence" / "autotask-business-context-exec-cap003-service.json"
    text = evidence_path.read_text(encoding="utf-8")
    assert '"focused_ticket_number": "T2"' in text
    assert '"raw_provider_content_persisted": false' in text


def test_invoker_accepts_focused_ticket_resolved_outside_bounded_company_list(tmp_path) -> None:
    analyzer = FakeAnalyzer()
    invoker = AutotaskBusinessContextInvoker(
        reader=FakeReader(),
        analyzer=analyzer,
        repository_root=tmp_path / "repository",
    )

    result = invoker.invoke(
        request=_request(tmp_path, ticket_number="T999"),
        resolution=_resolution(),
    )

    assert analyzer.focus_ticket_number == "T999"
    assert result.output["focused_ticket_number"] == "T999"
    assert result.output["record_counts"]["tickets"] == 3
