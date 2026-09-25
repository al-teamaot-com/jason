from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

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
from jason_runtime.autotask_internal_note import (
    AUTOTASK_INTERNAL_NOTE_AUTONOMY_EMAIL_ENV,
    AUTOTASK_INTERNAL_NOTE_PROFILE,
    AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
    AUTOTASK_INTERNAL_NOTE_PROVIDER,
    AutotaskInternalNoteActivationError,
    AutotaskInternalNoteConnector,
    AutotaskInternalNoteVerificationError,
    SERVICE_TICKET_NOTE_CREATE,
    configured_autotask_internal_note_autonomy_email,
    register_autotask_internal_note_runtime_foundation,
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


def _registries():
    return (
        CapabilityRegistryService(
            registry=InMemoryCapabilityRegistry()
        ),
        ExecutionProviderRegistryService(
            registry=InMemoryExecutionProviderRegistry()
        ),
    )


def test_internal_note_foundation_is_dormant_by_default(
    monkeypatch,
):
    monkeypatch.delenv(
        AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
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

    capabilities, providers = _registries()

    state = register_autotask_internal_note_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is False

    capability = capabilities.get(
        capability_name=SERVICE_TICKET_NOTE_CREATE,
        version="1.0",
    )

    provider = providers.get(
        AUTOTASK_INTERNAL_NOTE_PROVIDER
    )

    assert (
        capability.lifecycle_status
        is CapabilityLifecycle.BUILDING
    )

    assert capability.client_isolation_required is False

    assert (
        provider.lifecycle_status
        is ProviderLifecycle.PLANNED
    )

    assert (
        provider.health_status
        is ProviderHealth.UNKNOWN
    )

    assert (
        provider.approval_status
        is ProviderApproval.PILOT
    )


def test_exact_profile_activates_only_internal_note(
    monkeypatch,
):
    monkeypatch.setenv(
        AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
        AUTOTASK_INTERNAL_NOTE_PROFILE,
    )

    monkeypatch.setenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        "true",
    )

    monkeypatch.setenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    )

    capabilities, providers = _registries()

    state = register_autotask_internal_note_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is True

    assert state.capability_names == (
        SERVICE_TICKET_NOTE_CREATE,
    )

    assert state.provider_ids == (
        AUTOTASK_INTERNAL_NOTE_PROVIDER,
    )

    capability = capabilities.get_current(
        capability_name=SERVICE_TICKET_NOTE_CREATE,
    )

    provider = providers.get(
        AUTOTASK_INTERNAL_NOTE_PROVIDER
    )

    assert (
        capability.lifecycle_status
        is CapabilityLifecycle.ACTIVE
    )

    assert capability.client_isolation_required is False
    assert capability.approval.required is True
    assert capability.maximum_attempts == 1
    assert capability.idempotency_key_required is True

    assert (
        capability.metadata[
            "conversation_authenticated_imperative_is_approval"
        ]
        == "true"
    )

    assert provider.capabilities == frozenset(
        {
            SERVICE_TICKET_NOTE_CREATE,
        }
    )

    assert (
        provider.lifecycle_status
        is ProviderLifecycle.AVAILABLE
    )

    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED


def test_profile_fails_closed_without_mutation_gate(
    monkeypatch,
):
    monkeypatch.setenv(
        AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
        AUTOTASK_INTERNAL_NOTE_PROFILE,
    )

    monkeypatch.delenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        raising=False,
    )

    monkeypatch.setenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    )

    capabilities, providers = _registries()

    with pytest.raises(
        AutotaskInternalNoteActivationError,
        match="requires mutation execution",
    ):
        register_autotask_internal_note_runtime_foundation(
            capabilities=capabilities,
            providers=providers,
            now=datetime.now(timezone.utc),
        )


class _Secrets:
    def resolve(
        self,
        logical_name,
        context,
    ):
        del context

        assert logical_name == "autotask.write"

        return {
            "username": "write@example.invalid",
            "secret": "synthetic-secret",
            "integration_code": "synthetic-code",
        }


class _Audit:
    def __init__(self):
        self.events = []

    def record(
        self,
        event_type,
        context,
        details,
    ):
        del context

        self.events.append(
            (
                str(event_type),
                dict(details),
            )
        )


@dataclass(frozen=True)
class _Binding:
    jason_identity_id: str = "person-al"
    email_address: str = "al@example.com"


class _Bindings:
    def find_active_by_jason_identity(
        self,
        *,
        jason_identity_id,
    ):
        if jason_identity_id != "person-al":
            return None

        return _Binding()


class _Transport:
    def __init__(
        self,
        *,
        mismatch=False,
        resource_email="al@example.com",
        resource_id=77,
    ):
        self.requests: list[dict[str, Any]] = []
        self.mismatch = mismatch
        self.resource_email = resource_email
        self.resource_id = resource_id

    def request(
        self,
        *,
        method,
        url,
        headers,
        params=None,
        json=None,
        timeout_seconds=30.0,
    ):
        del timeout_seconds

        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "params": params,
                "json": json,
            }
        )

        if url.endswith(
            "/v1.0/zoneInformation"
        ):
            return {
                "url": (
                    "https://webservices3.autotask.net/"
                    "atservicesrest/"
                )
            }

        if url.endswith(
            "/V1.0/Resources/query"
        ):
            return {
                "items": [
                    {
                        "id": self.resource_id,
                        "email": self.resource_email,
                        "isActive": True,
                    }
                ]
            }

        if url.endswith(
            "/V1.0/TicketNotes/entityInformation"
        ):
            return {
                "userAccessForCreate": 1,
                "userAccessForUpdate": 1,
            }

        if (
            method == "POST"
            and url.endswith(
                "/V1.0/Tickets/12345/Notes"
            )
        ):
            return {
                "itemId": 222,
            }

        if (
            method == "GET"
            and url.endswith(
                "/V1.0/Tickets/12345/Notes"
            )
        ):
            return {
                "items": [
                    {
                        "id": 222,
                        "title": "Jason internal note",
                        "description": (
                            "WRONG"
                            if self.mismatch
                            else "Synthetic internal note"
                        ),
                        "noteType": 3,
                        "publish": 1,
                        "creatorResourceID": self.resource_id,
                        "impersonatorCreatorResourceID": 999,
                    }
                ]
            }

        raise AssertionError(
            f"unexpected transport request: {method} {url}"
        )


def _connector_request(principal_id="person-al"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-internal-note",
            principal_id=principal_id,
            organization_id="aot",
            client_id=None,
            capability="autotask.ticket.note.create",
            mode="execute",
        ),
        arguments={
            "payload": {
                "ticketID": 12345,
                "title": "Jason internal note",
                "description": "Synthetic internal note",
                "noteType": 3,
                "publish": 1,
            }
        },
    )


def _connector(
    transport,
    audit,
    *,
    autonomy_principal_email=None,
):
    return AutotaskInternalNoteConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=audit,
        bindings=_Bindings(),
        autonomy_principal_email=autonomy_principal_email,
    )


def _enable_mutation(
    monkeypatch,
):
    monkeypatch.setenv(
        AUTOTASK_MUTATION_ENABLED_ENV,
        "true",
    )

    monkeypatch.setenv(
        AUTOTASK_REQUESTER_AUTH_MODE_ENV,
        AUTOTASK_AUTH_MODE_JASON_MANAGED,
    )


def test_internal_note_connector_requires_successful_readback(
    monkeypatch,
):
    _enable_mutation(
        monkeypatch
    )

    transport = _Transport()
    audit = _Audit()

    result = _connector(
        transport,
        audit,
    ).execute(
        _connector_request()
    )

    assert result.data[
        "jasonVerification"
    ] == {
        "readbackVerified": True,
        "ticketNoteId": 222,
        "creatorResourceId": 77,
        "impersonatorRecorded": True,
    }

    assert result.evidence_ids == (
        "autotask:ticket-note:222",
    )

    methods = [
        request["method"]
        for request in transport.requests
    ]

    assert methods.count("POST") == 1
    assert methods.count("PATCH") == 0
    assert methods.count("DELETE") == 0

    assert (
        "connector.mutation.verified",
        {
            "provider": "autotask",
            "capability": "autotask.ticket.note.create",
            "ticket_note_id": 222,
        },
    ) in audit.events


def test_internal_note_connector_never_retries_post_when_readback_fails(
    monkeypatch,
):
    _enable_mutation(
        monkeypatch
    )

    transport = _Transport(
        mismatch=True
    )

    audit = _Audit()

    with pytest.raises(
        AutotaskInternalNoteVerificationError,
        match="description failed readback",
    ):
        _connector(
            transport,
            audit,
        ).execute(
            _connector_request()
        )

    methods = [
        request["method"]
        for request in transport.requests
    ]

    assert methods.count("POST") == 1
    assert methods.count("PATCH") == 0
    assert methods.count("DELETE") == 0

    assert any(
        event == "connector.mutation.verification_failed"
        for event, _ in audit.events
    )


def test_autonomy_email_configuration_is_default_empty_and_aot_only(monkeypatch):
    monkeypatch.delenv(AUTOTASK_INTERNAL_NOTE_AUTONOMY_EMAIL_ENV, raising=False)
    assert configured_autotask_internal_note_autonomy_email() is None

    monkeypatch.setenv(
        AUTOTASK_INTERNAL_NOTE_AUTONOMY_EMAIL_ENV,
        "JasonRW@teamaot.com",
    )
    assert (
        configured_autotask_internal_note_autonomy_email()
        == "jasonrw@teamaot.com"
    )

    monkeypatch.setenv(
        AUTOTASK_INTERNAL_NOTE_AUTONOMY_EMAIL_ENV,
        "attacker@example.com",
    )
    with pytest.raises(
        RuntimeError,
        match="AUTOTASK_INTERNAL_NOTE_AUTONOMY_EMAIL_INVALID",
    ):
        configured_autotask_internal_note_autonomy_email()


def test_autonomous_service_principal_uses_explicit_internal_note_mapping(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
    )
    audit = _Audit()

    result = _connector(
        transport,
        audit,
        autonomy_principal_email="jasonRW@teamaot.com",
    ).execute(
        _connector_request("jason-autonomy-worker")
    )

    assert result.data["jasonVerification"] == {
        "readbackVerified": True,
        "ticketNoteId": 222,
        "creatorResourceId": 29682930,
        "impersonatorRecorded": True,
    }

    posts = [
        request
        for request in transport.requests
        if request["method"] == "POST"
    ]
    assert len(posts) == 1
    assert posts[0]["headers"]["ImpersonationResourceId"] == "29682930"


def test_autonomous_service_principal_mapping_is_not_available_to_other_services(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
    )

    with pytest.raises(
        PermissionError,
        match="AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED",
    ):
        _connector(
            transport,
            _Audit(),
            autonomy_principal_email="jasonrw@teamaot.com",
        ).execute(
            _connector_request("some-other-service")
        )

    assert not any(
        request["method"] == "POST"
        for request in transport.requests
    )


def test_autonomous_service_principal_fails_closed_without_mapping(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
    )

    with pytest.raises(
        PermissionError,
        match="AUTOTASK_TRUSTED_PRINCIPAL_BINDING_REQUIRED",
    ):
        _connector(
            transport,
            _Audit(),
        ).execute(
            _connector_request("jason-autonomy-worker")
        )

    assert not any(
        request["method"] == "POST"
        for request in transport.requests
    )
