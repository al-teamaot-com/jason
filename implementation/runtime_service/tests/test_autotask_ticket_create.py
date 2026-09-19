from datetime import datetime, timezone

import pytest

from connectors.autotask.mutation_connector import AUTOTASK_MUTATION_ENABLED_ENV
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime.autotask_ticket_create import (
    AUTOTASK_TICKET_CREATE_PROFILE,
    AUTOTASK_TICKET_CREATE_PROFILE_ENV,
    AUTOTASK_TICKET_CREATE_PROVIDER,
    SAFE_TICKET_CREATE_FIELDS,
    AutotaskTicketCreateConnector,
    register_autotask_ticket_create_runtime_foundation,
)
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.provider_mutation_capability_catalog import SERVICE_TICKET_CREATE


def registries():
    return (
        CapabilityRegistryService(registry=InMemoryCapabilityRegistry()),
        ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry()),
    )


def request(payload):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-create-test",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability="autotask.ticket.create",
            mode="execute",
        ),
        arguments={"payload": payload},
    )


def test_ticket_create_is_dormant_by_default(monkeypatch):
    monkeypatch.delenv(AUTOTASK_TICKET_CREATE_PROFILE_ENV, raising=False)
    monkeypatch.delenv(AUTOTASK_MUTATION_ENABLED_ENV, raising=False)
    capabilities, providers = registries()
    state = register_autotask_ticket_create_runtime_foundation(
        capabilities=capabilities, providers=providers, now=datetime.now(timezone.utc)
    )
    assert state.enabled is False
    assert capabilities.get(
        capability_name=SERVICE_TICKET_CREATE, version="1.0"
    ).lifecycle_status is CapabilityLifecycle.BUILDING
    assert providers.get(AUTOTASK_TICKET_CREATE_PROVIDER).lifecycle_status is ProviderLifecycle.PLANNED


def test_exact_profile_activates_ticket_create(monkeypatch):
    monkeypatch.setenv(AUTOTASK_TICKET_CREATE_PROFILE_ENV, AUTOTASK_TICKET_CREATE_PROFILE)
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")
    capabilities, providers = registries()
    state = register_autotask_ticket_create_runtime_foundation(
        capabilities=capabilities, providers=providers, now=datetime.now(timezone.utc)
    )
    assert state.enabled is True
    capability = capabilities.get_current(capability_name=SERVICE_TICKET_CREATE)
    provider = providers.get(AUTOTASK_TICKET_CREATE_PROVIDER)
    assert capability.lifecycle_status is CapabilityLifecycle.ACTIVE
    assert capability.approval.required is True
    assert capability.maximum_attempts == 1
    assert capability.metadata["mcp_action_enabled"] == "true"
    assert set(capability.metadata["safe_create_fields"].split(",")) == SAFE_TICKET_CREATE_FIELDS
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED


def test_ticket_create_payload_is_bounded():
    payload = AutotaskTicketCreateConnector.validated_payload(
        request({
            "companyID": 100,
            "title": "SET-01 - Windows Security Log unreadable",
            "description": "Governed remediation tracking",
            "status": 1,
            "priority": 2,
            "queueID": 29682833,
            "configurationItemID": 1120,
        })
    )
    assert payload["companyID"] == 100
    assert payload["title"].startswith("SET-01")
    assert set(payload) <= SAFE_TICKET_CREATE_FIELDS


def test_ticket_create_rejects_unknown_fields():
    with pytest.raises(PermissionError, match="AUTOTASK_TICKET_CREATE_FIELD_NOT_ALLOWED"):
        AutotaskTicketCreateConnector.validated_payload(
            request({"companyID": 100, "title": "x", "id": 9})
        )
