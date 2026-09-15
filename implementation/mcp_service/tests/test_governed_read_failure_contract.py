from types import SimpleNamespace

from jason_mcp import server
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)


class _AllowedAuthority:
    def evaluate(self, request):
        return SimpleNamespace(
            outcome=server.AuthorityOutcome.ALLOWED,
            reason_codes=("authorized",),
            execution_context=SimpleNamespace(
                context_id="ctx-governed-read-failure",
                approval_required=False,
            ),
        )


class _FailedOrchestrator:
    def execute(self, request):
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            status=OrchestrationStatus.FAILED,
            stage=ExecutionStage.FAILED,
            reason_codes=("capability_invocation_failed",),
            resolution=None,
            output=None,
            attempts=1,
            provider_id="autotask-live-read",
            error_code="CAPABILITY_INVOCATION_FAILED",
        )


def test_governed_read_returns_structured_failure_when_output_is_absent(
    monkeypatch,
):
    monkeypatch.setattr(
        server,
        "_authenticated_identity",
        lambda: (
            "person-al",
            "aot",
            "entra-oauth-bearer",
            None,
        ),
    )
    monkeypatch.setattr(
        server,
        "_runtime",
        lambda: SimpleNamespace(
            identity_authority=_AllowedAuthority(),
            governed_orchestrator=_FailedOrchestrator(),
        ),
    )

    result = server._governed_read(
        capability_name="service.ticket.search",
        arguments={"filters": {"companyID": 1}},
    )

    assert result["status"] == "failed"
    assert result["stage"] == "failed"
    assert result["capability"] == "service.ticket.search"
    assert result["provider"] == "autotask-live-read"
    assert result["reason_codes"] == [
        "capability_invocation_failed"
    ]
    assert result["error_code"] == "CAPABILITY_INVOCATION_FAILED"
    assert result["evidence"] == {}
