from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from connectors.autotask.impersonating_connector import (
    AUTOTASK_AUTH_MODE_JASON_MANAGED,
    AUTOTASK_REQUESTER_AUTH_MODE_ENV,
)
from connectors.autotask.mutation_connector import (
    AUTOTASK_MUTATION_ENABLED_ENV,
)
from connectors.core.contracts import (
    ConnectorContext,
    ConnectorRequest,
)
from jason_runtime.autotask_ticket_update import (
    AUTOTASK_TICKET_UPDATE_PROFILE,
    AUTOTASK_TICKET_UPDATE_PROFILE_ENV,
    AUTOTASK_TICKET_UPDATE_PROVIDER,
    SAFE_TICKET_UPDATE_FIELDS,
    AutotaskTicketUpdateConnector,
    register_autotask_ticket_update_runtime_foundation,
)
from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_TICKET_UPDATE,
)


def registries():
    return (
        CapabilityRegistryService(
            registry=InMemoryCapabilityRegistry()
        ),
        ExecutionProviderRegistryService(
            registry=InMemoryExecutionProviderRegistry()
        ),
    )


def test_ticket_update_is_dormant_by_default(monkeypatch):
    monkeypatch.delenv(
        AUTOTASK_TICKET_UPDATE_PROFILE_ENV,
        raising=False,
    )
    monkeypatch.delenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        raising=False,
    )
    monkeypatch.delenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        raising=False,
    )

    capabilities, providers = registries()

    state = register_autotask_ticket_update_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is False

    capability = capabilities.get(
        capability_name=SERVICE_TICKET_UPDATE,
        version="1.0",
    )

    provider = providers.get(
        AUTOTASK_TICKET_UPDATE_PROVIDER
    )

    assert (
        capability.lifecycle_status
        is CapabilityLifecycle.BUILDING
    )

    assert (
        provider.lifecycle_status
        is ProviderLifecycle.PLANNED
    )


def test_exact_profile_activates_generic_ticket_update(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_TICKET_UPDATE_PROFILE_ENV,
        AUTOTASK_TICKET_UPDATE_PROFILE,
    )
    monkeypatch.setenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        "true",
    )
    monkeypatch.setenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    )

    capabilities, providers = registries()

    state = register_autotask_ticket_update_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is True
    assert state.capability_names == (
        SERVICE_TICKET_UPDATE,
    )

    capability = capabilities.get_current(
        capability_name=SERVICE_TICKET_UPDATE
    )

    provider = providers.get(
        AUTOTASK_TICKET_UPDATE_PROVIDER
    )

    assert (
        capability.lifecycle_status
        is CapabilityLifecycle.ACTIVE
    )

    assert capability.approval.required is True
    assert capability.maximum_attempts == 1
    assert capability.idempotency_key_required is True

    assert (
        capability.metadata["mcp_action_enabled"]
        == "true"
    )

    assert (
        set(
            capability.metadata[
                "safe_update_fields"
            ].split(",")
        )
        == SAFE_TICKET_UPDATE_FIELDS
    )

    assert (
        provider.lifecycle_status
        is ProviderLifecycle.AVAILABLE
    )

    assert (
        provider.health_status
        is ProviderHealth.HEALTHY
    )

    assert (
        provider.approval_status
        is ProviderApproval.APPROVED
    )


def request(payload):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-test",
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
            capability="autotask.ticket.update",
            mode="execute",
        ),
        arguments={
            "payload": payload,
        },
    )


def test_ticket_update_payload_allows_only_safe_fields():
    payload = AutotaskTicketUpdateConnector.validated_payload(
        request(
            {
                "id": 12345,
                "status": 1,
                "priority": 2,
                "queueID": 3,
                "assignedResourceID": 4,
                "dueDateTime": "2026-09-16T17:00:00Z",
            }
        )
    )

    assert payload["id"] == 12345
    assert set(payload) == {
        "id",
        "status",
        "priority",
        "queueID",
        "assignedResourceID",
        "dueDateTime",
    }
    assert set(payload) - {"id"} <= SAFE_TICKET_UPDATE_FIELDS




def test_ticket_update_payload_accepts_work_lifecycle_fields():
    payload = AutotaskTicketUpdateConnector.validated_payload(
        request(
            {
                "id": 12345,
                "configurationItemID": 1120,
                "billingCodeID": 29682801,
                "issueType": 10,
                "subIssueType": 104,
                "ticketType": 1,
            }
        )
    )

    assert payload == {
        "id": 12345,
        "configurationItemID": 1120,
        "billingCodeID": 29682801,
        "issueType": 10,
        "subIssueType": 104,
        "ticketType": 1,
    }


def test_ticket_picklist_label_resolution_honors_parent_value():
    fields_payload = {
        "fields": [
            {
                "name": "issueType",
                "picklistValues": [
                    {"value": "10", "label": "Hardware", "isActive": True},
                ],
            },
            {
                "name": "subIssueType",
                "picklistValues": [
                    {
                        "value": "104",
                        "label": "Workstation",
                        "parentValue": "10",
                        "isActive": True,
                    },
                    {
                        "value": "999",
                        "label": "Workstation",
                        "parentValue": "11",
                        "isActive": True,
                    },
                ],
            },
        ]
    }

    assert (
        AutotaskTicketUpdateConnector._picklist_value_for_label(
            fields_payload=fields_payload,
            field_name="issueType",
            label="Hardware",
        )
        == 10
    )
    assert (
        AutotaskTicketUpdateConnector._picklist_value_for_label(
            fields_payload=fields_payload,
            field_name="subIssueType",
            label="Workstation",
            parent_value=10,
        )
        == 104
    )


def test_symbolic_label_detection_keeps_numeric_strings_numeric():
    assert AutotaskTicketUpdateConnector._label_requires_resolution("Jason") is True
    assert AutotaskTicketUpdateConnector._label_requires_resolution("29682833") is False
    assert AutotaskTicketUpdateConnector._label_requires_resolution(29682833) is False


@pytest.mark.parametrize(
    "payload",
    [
        {"id": 12345},
        {"id": 12345, "title": "not allowed"},
        {"id": 0, "status": 1},
        {"id": 12345, "status": 0},
    ],
)
def test_ticket_update_payload_fails_closed(payload):
    with pytest.raises(
        (ValueError, PermissionError)
    ):
        AutotaskTicketUpdateConnector.validated_payload(
            request(payload)
        )


def test_ticket_update_readback_verifies_every_requested_field():
    expected = {
        "id": 12345,
        "status": 1,
        "priority": 2,
        "queueID": 3,
    }

    observed = {
        "id": 12345,
        "status": 1,
        "priority": 2,
        "queueID": 3,
        "title": "unchanged",
    }

    AutotaskTicketUpdateConnector._verify(
        expected=expected,
        observed=observed,
    )


def test_ticket_update_readback_rejects_mismatch():
    with pytest.raises(Exception):
        AutotaskTicketUpdateConnector._verify(
            expected={
                "id": 12345,
                "status": 1,
            },
            observed={
                "id": 12345,
                "status": 2,
            },
        )
