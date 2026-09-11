from decimal import Decimal

import pytest

from connectors.core.contracts import (
    ConnectorCredentialUnavailableError,
    ConnectorTransportError,
)
from connectors.core.openbao_secrets import (
    OpenBaoAuthenticationError,
    OpenBaoSecretResolutionError,
    OpenBaoTransportError,
)
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import (
    CapabilityResolutionResult,
    CapabilityResolutionStatus,
    ResolutionOutcome,
)
from orchestrator import (
    CentralOrchestrator,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationStatus,
)


class Resolution:
    def resolve(self, request):
        return CapabilityResolutionResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            capability_version="1.0.0",
            outcome=ResolutionOutcome.RESOLVED,
            capability_status=CapabilityResolutionStatus.RESOLVED_CURRENT,
            reason_codes=("resolved",),
            eligible_provider_ids=("provider-1",),
            selected_provider_id="provider-1",
        )


class FailingInvoker:
    def __init__(self, error):
        self.error = error

    def invoke(self, *, request, resolution):
        del request, resolution
        raise self.error


class Audit:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload):
        self.events.append((event_type, dict(payload)))


def _request():
    return OrchestrationRequest(
        execution_id="exec-safe-failure",
        correlation_id="corr-safe-failure",
        principal_id="person-al",
        organization_id="aot",
        capability_name="autotask.ticket.search",
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
        arguments={"ticket_number": "T1"},
    )


@pytest.mark.parametrize(
    ("error", "expected_code"),
    (
        (
            ConnectorCredentialUnavailableError("RoleID file is unavailable."),
            "CONNECTOR_CREDENTIAL_UNAVAILABLE",
        ),
        (
            OpenBaoAuthenticationError("OpenBao AppRole authentication failed."),
            "OPENBAO_AUTH_FAILED",
        ),
        (
            OpenBaoSecretResolutionError("OpenBao secret resolution failed."),
            "OPENBAO_SECRET_RESOLUTION_FAILED",
        ),
        (
            OpenBaoTransportError("OpenBao transport failed."),
            "OPENBAO_TRANSPORT_FAILURE",
        ),
        (
            ConnectorTransportError("HTTP failure", status_code=401),
            "PROVIDER_HTTP_STATUS_401",
        ),
        (
            ConnectorTransportError("transport failure"),
            "PROVIDER_TRANSPORT_FAILURE",
        ),
    ),
)
def test_safe_failure_code_survives_orchestration_without_exception_text(
    error,
    expected_code,
):
    audit = Audit()
    result = CentralOrchestrator(
        resolution=Resolution(),
        invoker=FailingInvoker(error),
        audit=audit,
    ).execute(_request())

    assert result.status is OrchestrationStatus.FAILED
    assert result.error_code == expected_code
    assert result.reason_codes == ("capability_invocation_failed",)
    assert expected_code in repr(audit.events)
    assert str(error) not in repr(result) + repr(audit.events)
