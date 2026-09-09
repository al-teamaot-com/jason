from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_policy import (
    CostEstimator,
    DataHandlingPolicy,
    ExecutionBudget,
    ExecutionPolicyEngine,
    InMemoryPricingRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from kernel.resolution import GovernedCapabilityResolutionEngine
from orchestrator.contracts import (
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationStatus,
)
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_TICKET_SEARCH,
    register_provider_read_foundation,
)
from orchestrator.service import CentralOrchestrator
from jason_runtime.provider_reads import build_provider_read_invoker


NOW = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)


class _Secrets:
    def __init__(self) -> None:
        self.resolutions: list[tuple[str, str, str, str]] = []

    def resolve(self, logical_name, context):
        self.resolutions.append(
            (
                logical_name,
                context.capability,
                context.organization_id,
                context.mode,
            )
        )
        if logical_name == "it_glue.readonly":
            return {"api_key": "test-only-it-glue-key"}
        if logical_name == "autotask.readonly":
            return {
                "integration_code": "test-only-integration-code",
                "username": "test-only-user@example.invalid",
                "secret": "test-only-autotask-secret",
            }
        raise AssertionError(f"unexpected logical secret: {logical_name}")


class _Transport:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Mapping[str, Any]:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "header_names": tuple(sorted(headers)),
                "params": dict(params or {}),
                "json": dict(json or {}),
                "timeout_seconds": timeout_seconds,
            }
        )
        if url.endswith("/zoneInformation"):
            return {"url": "https://example.autotask.invalid/atservicesrest"}
        if url == "https://api.itglue.com/organizations":
            return {
                "data": [
                    {
                        "id": "208",
                        "type": "organizations",
                        "attributes": {"name": "Hitt Electric"},
                    }
                ],
                "meta": {"current-page": 1, "total-pages": 1},
            }
        if url == "https://example.autotask.invalid/atservicesrest/V1.0/Tickets/query":
            return {
                "items": [
                    {
                        "id": 901,
                        "ticketNumber": "T20260909.0012",
                        "companyID": 77,
                        "title": "Printer issue",
                        "status": 1,
                    }
                ]
            }
        raise AssertionError(f"unexpected provider request: {method} {url}")


class _Audit:
    def __init__(self) -> None:
        self.connector_events: list[tuple[str, str, Mapping[str, Any]]] = []
        self.orchestration_events: list[tuple[str, Mapping[str, Any]]] = []

    def record(self, event_type, context, details):
        self.connector_events.append((event_type, context.capability, dict(details)))

    def append(self, event_type, payload):
        self.orchestration_events.append((event_type, dict(payload)))


def _foundation():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )
    return capabilities, providers


def _activate_in_memory(capabilities, providers, *, provider_id: str, capability_name: str) -> None:
    providers.set_health(
        provider_id=provider_id,
        health_status=ProviderHealth.HEALTHY,
    )
    providers.set_approval(
        provider_id=provider_id,
        approval_status=ProviderApproval.APPROVED,
    )
    providers.set_lifecycle(
        provider_id=provider_id,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
    )
    capabilities.set_lifecycle(
        capability_name=capability_name,
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )


def _orchestrator(capabilities, providers, secrets, transport, audit) -> CentralOrchestrator:
    resolution = GovernedCapabilityResolutionEngine(
        capabilities=capabilities,
        providers=providers,
        policy=ExecutionPolicyEngine(
            cost_estimator=CostEstimator(InMemoryPricingRegistry())
        ),
    )
    return CentralOrchestrator(
        resolution=resolution,
        invoker=build_provider_read_invoker(
            secrets=secrets,
            transport=transport,
            audit=audit,
        ),
        audit=audit,
    )


def _request(capability_name: str, arguments: Mapping[str, Any]) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id=f"exec-{capability_name}",
        correlation_id=f"corr-{capability_name}",
        principal_id="person-al",
        organization_id="org-aot",
        client_id="client-aot-internal",
        capability_name=capability_name,
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
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
            maximum_attempts=1,
        ),
        arguments=arguments,
        permission_mode="observe",
    )


def test_source_defaults_fail_closed_before_provider_backed_activation() -> None:
    capabilities, providers = _foundation()
    secrets = _Secrets()
    transport = _Transport()
    audit = _Audit()

    result = _orchestrator(capabilities, providers, secrets, transport, audit).execute(
        _request(
            DOCUMENTATION_ORGANIZATION_SEARCH,
            {"name": "Hitt Electric"},
        )
    )

    assert result.status is OrchestrationStatus.DENIED
    assert result.attempts == 0
    assert result.output == {}
    assert secrets.resolutions == []
    assert transport.requests == []


def test_it_glue_read_runs_chatgpt_ready_canonical_path_through_central_orchestrator() -> None:
    capabilities, providers = _foundation()
    _activate_in_memory(
        capabilities,
        providers,
        provider_id=IT_GLUE_PROVIDER,
        capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
    )
    secrets = _Secrets()
    transport = _Transport()
    audit = _Audit()

    result = _orchestrator(capabilities, providers, secrets, transport, audit).execute(
        _request(
            DOCUMENTATION_ORGANIZATION_SEARCH,
            {"name": "Hitt Electric", "page_size": 25},
        )
    )

    assert result.status is OrchestrationStatus.SUCCEEDED
    assert result.provider_id == IT_GLUE_PROVIDER
    assert result.output["provider"] == IT_GLUE_PROVIDER
    assert result.output["provider_capability"] == "it_glue.entity.query"
    assert result.output["data"]["data"][0]["attributes"]["name"] == "Hitt Electric"
    assert secrets.resolutions == [
        (
            "it_glue.readonly",
            "it_glue.entity.query",
            "org-aot",
            "observe",
        )
    ]
    assert transport.requests == [
        {
            "method": "GET",
            "url": "https://api.itglue.com/organizations",
            "header_names": ("Accept", "x-api-key"),
            "params": {"filter[name]": "Hitt Electric", "page[size]": 25},
            "json": {},
            "timeout_seconds": 30.0,
        }
    ]
    assert result.resolution is not None
    assert result.resolution.execution_plan is not None
    assert result.resolution.execution_plan.model_id is None
    assert result.resolution.execution_plan.estimated_cost.total_estimated_cost == Decimal("0")


def test_autotask_read_runs_same_governed_path_with_bounded_structured_query() -> None:
    capabilities, providers = _foundation()
    _activate_in_memory(
        capabilities,
        providers,
        provider_id=AUTOTASK_PROVIDER,
        capability_name=SERVICE_TICKET_SEARCH,
    )
    secrets = _Secrets()
    transport = _Transport()
    audit = _Audit()

    result = _orchestrator(capabilities, providers, secrets, transport, audit).execute(
        _request(
            SERVICE_TICKET_SEARCH,
            {
                "ticket_number": "T20260909.0012",
                "company_id": 77,
                "page_size": 50,
            },
        )
    )

    assert result.status is OrchestrationStatus.SUCCEEDED
    assert result.provider_id == AUTOTASK_PROVIDER
    assert result.output["provider"] == AUTOTASK_PROVIDER
    assert result.output["provider_capability"] == "autotask.ticket.search"
    assert result.output["data"]["items"][0]["ticketNumber"] == "T20260909.0012"
    assert secrets.resolutions == [
        (
            "autotask.readonly",
            "autotask.ticket.search",
            "org-aot",
            "observe",
        )
    ]
    assert len(transport.requests) == 2
    assert transport.requests[0]["url"].endswith("/zoneInformation")
    assert transport.requests[0]["params"] == {"user": "test-only-user@example.invalid"}
    provider_request = transport.requests[1]
    assert provider_request["method"] == "GET"
    assert provider_request["url"] == (
        "https://example.autotask.invalid/atservicesrest/V1.0/Tickets/query"
    )
    assert json.loads(provider_request["params"]["search"]) == {
        "MaxRecords": 50,
        "filter": [
            {"op": "eq", "field": "ticketNumber", "value": "T20260909.0012"},
            {"op": "eq", "field": "companyID", "value": 77},
        ],
    }
    assert result.resolution is not None
    assert result.resolution.execution_plan is not None
    assert result.resolution.execution_plan.model_id is None
    assert result.resolution.execution_plan.estimated_cost.total_estimated_cost == Decimal("0")
    assert any(
        event_type == "orchestration.capability.completed"
        for event_type, _ in audit.orchestration_events
    )
