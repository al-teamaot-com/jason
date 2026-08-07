from __future__ import annotations

import json
from decimal import Decimal

from connectors.autotask.live_read import (
    AutotaskLiveReadEvidence,
    AutotaskTicketSnapshot,
)
from jason_cap_002.local_llm import TicketBriefing
from jason_cap_002.service import TicketIntelligenceInvoker
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import (
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator import OrchestrationMode, OrchestrationRequest


class FakeAutotask:
    def read_ticket(self, request, *, output_path, repository_root=None):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('{"status":"approved"}\n', encoding="utf-8")
        output_path.chmod(0o600)
        return (
            AutotaskTicketSnapshot(
                ticket_number=request.ticket_number,
                company_id="208",
                title="Raw sensitive title",
                description="Raw sensitive description",
                created_at="2026-08-05T17:16:45.500Z",
                updated_at=None,
                configuration_item_id=None,
                requester_identity_id=None,
            ),
            AutotaskLiveReadEvidence(
                schema_version="1.1",
                provider="autotask",
                capability="autotask.ticket.search",
                logical_secret="autotask.readonly",
                scope_name=request.scope_name,
                ticket_number=request.ticket_number,
                discovered_company_id="208",
                company_boundary_source="autotask-ticket",
                retrieved_at="2026-08-07T10:00:00+00:00",
                configuration_item_id=None,
                requester_identity_id=None,
                created_at="2026-08-05T17:16:45.500Z",
                updated_at=None,
                title_sha256="a" * 64,
                description_sha256="b" * 64,
                evidence_sha256="c" * 64,
                protected_values_exposed=False,
                status="approved",
            ),
        )


class FakeAnalyzer:
    model = "qwen3:1.7b"

    def analyze(self, ticket):
        return TicketBriefing(
            model=self.model,
            summary="Application launch issue requires diagnosis.",
            likely_causes=("Service unavailable.",),
            recommended_steps=("Verify the service state.",),
            escalation_flags=(),
            confidence="medium",
        )


def test_ticket_intelligence_writes_derived_artifacts_without_raw_source(tmp_path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    evidence_directory = tmp_path / "evidence"
    request = OrchestrationRequest(
        execution_id="exec-cap002",
        correlation_id="corr-cap002",
        principal_id="operator-al",
        organization_id="aot",
        capability_name="support.ticket.analyze",
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
            maximum_attempts=1,
        ),
        arguments={
            "ticket_number": "T20260805.0064",
            "scope": "aot-internal-ticket-analysis",
            "allowed_scope": "aot-internal-ticket-analysis",
            "evidence_directory": str(evidence_directory),
        },
    )
    resolution = CapabilityResolutionResult(
        execution_id=request.execution_id,
        correlation_id=request.correlation_id,
        capability_name=request.capability_name,
        capability_version="1.0",
        outcome=ResolutionOutcome.RESOLVED,
        capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
        reason_codes=("resolved",),
        eligible_provider_ids=("jason.local-ticket-intelligence",),
        selected_provider_id="jason.local-ticket-intelligence",
    )

    result = TicketIntelligenceInvoker(
        autotask=FakeAutotask(),
        analyzer=FakeAnalyzer(),
        repository_root=repository,
    ).invoke(request=request, resolution=resolution)

    assert result.output["provider_side_change"] is False
    assert len(result.artifact_references) == 3
    for artifact in result.artifact_references:
        assert artifact.sha256 is not None

    evidence_path = next(
        path for path in evidence_directory.iterdir()
        if path.name.startswith("ticket-intelligence-")
    )
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["local_processing_only"] is True
    assert payload["provider_side_change"] is False
    assert payload["raw_ticket_content_persisted"] is False
    assert "Raw sensitive title" not in evidence_path.read_text(encoding="utf-8")
    assert "Raw sensitive description" not in evidence_path.read_text(encoding="utf-8")
    assert evidence_path.stat().st_mode & 0o777 == 0o600
