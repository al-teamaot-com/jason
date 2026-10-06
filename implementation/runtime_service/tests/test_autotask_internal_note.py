from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
)
from jason_runtime.autotask_internal_note import (
    AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_ENV,
    AUTOTASK_INTERNAL_NOTE_PROFILE,
    AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
    AUTOTASK_INTERNAL_NOTE_PROVIDER,
    AutotaskInternalNoteActivationError,
    AutotaskInternalNoteConnector,
    AutotaskInternalNoteVerificationError,
    SERVICE_TICKET_NOTE_CREATE,
    SERVICE_TICKET_NOTE_UPDATE,
    configured_autotask_internal_note_autonomy_resource_id,
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
    update_capability = capabilities.get(
        capability_name=SERVICE_TICKET_NOTE_UPDATE,
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
    assert update_capability.lifecycle_status is CapabilityLifecycle.BUILDING
    assert update_capability.client_isolation_required is False

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
        SERVICE_TICKET_NOTE_UPDATE,
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
            SERVICE_TICKET_NOTE_UPDATE,
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
        note_creator_id=None,
        note_title="Jason internal note",
        note_description="Synthetic internal note",
    ):
        self.requests: list[dict[str, Any]] = []
        self.mismatch = mismatch
        self.resource_email = resource_email
        self.resource_id = resource_id
        self.note_creator_id = resource_id if note_creator_id is None else int(note_creator_id)
        self.note_title = note_title
        self.note_description = note_description

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
            if isinstance(json, Mapping):
                self.note_title = str(json.get("title") or self.note_title)
                self.note_description = str(json.get("description") or self.note_description)
            return {
                "itemId": 222,
            }

        if (
            method == "PATCH"
            and url.endswith(
                "/V1.0/Tickets/12345/Notes"
            )
        ):
            if not isinstance(json, Mapping) or int(json.get("id") or 0) != 222:
                raise AssertionError("unexpected update payload")
            self.note_title = str(json.get("title") or self.note_title)
            self.note_description = str(json.get("description") or self.note_description)
            return {"itemId": 222}

        if (
            method == "GET"
            and url.endswith(
                "/V1.0/Tickets/12345/Notes"
            )
        ):
            impersonator = (
                999
                if "ImpersonationResourceId" in headers
                else None
            )
            return {
                "items": [
                    {
                        "id": 222,
                        "title": self.note_title,
                        "description": (
                            "WRONG"
                            if self.mismatch
                            else self.note_description
                        ),
                        "noteType": 3,
                        "publish": 2,
                        "creatorResourceID": self.note_creator_id,
                        "impersonatorCreatorResourceID": impersonator,
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
                "publish": 2,
            }
        },
    )


def _connector(
    transport,
    audit,
    *,
    autonomy_api_resource_id=None,
):
    return AutotaskInternalNoteConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=audit,
        bindings=_Bindings(),
        autonomy_api_resource_id=autonomy_api_resource_id,
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


def test_autonomy_resource_id_configuration_is_default_empty_and_positive(monkeypatch):
    monkeypatch.delenv(
        AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_ENV,
        raising=False,
    )
    assert configured_autotask_internal_note_autonomy_resource_id() is None

    monkeypatch.setenv(
        AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_ENV,
        "29682930",
    )
    assert (
        configured_autotask_internal_note_autonomy_resource_id()
        == 29682930
    )

    for bad in ("0", "-1", "not-an-id"):
        monkeypatch.setenv(
            AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_ENV,
            bad,
        )
        with pytest.raises(
            RuntimeError,
            match="AUTOTASK_INTERNAL_NOTE_AUTONOMY_RESOURCE_ID_INVALID",
        ):
            configured_autotask_internal_note_autonomy_resource_id()


def test_autonomous_service_principal_uses_direct_api_user_attribution(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
    )
    audit = _Audit()

    result = _connector(
        transport,
        audit,
        autonomy_api_resource_id=29682930,
    ).execute(
        _connector_request("jason-autonomy-worker")
    )

    assert result.data["jasonVerification"] == {
        "readbackVerified": True,
        "ticketNoteId": 222,
        "creatorResourceId": 29682930,
        "impersonatorRecorded": False,
    }

    posts = [
        request
        for request in transport.requests
        if request["method"] == "POST"
    ]
    assert len(posts) == 1
    assert "ImpersonationResourceId" not in posts[0]["headers"]

    preflights = [
        request
        for request in transport.requests
        if request["method"] == "GET"
        and request["url"].endswith(
            "/V1.0/TicketNotes/entityInformation"
        )
    ]
    assert len(preflights) == 1
    assert "ImpersonationResourceId" not in preflights[0]["headers"]


def test_autonomous_api_user_mode_is_not_available_to_other_services(monkeypatch):
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
            autonomy_api_resource_id=29682930,
        ).execute(
            _connector_request("some-other-service")
        )

    assert not any(
        request["method"] == "POST"
        for request in transport.requests
    )


def test_autonomous_service_principal_fails_closed_without_api_resource_id(monkeypatch):
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


def _update_connector_request(
    *,
    current: str,
    replacement: str,
    title: str = "GPT Insights",
    mode: str = "replace",
    expected_hash: str | None = None,
):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-internal-note-update",
            principal_id="jason-autonomy-worker",
            organization_id="aot",
            client_id=None,
            capability="autotask.ticket.note.update",
            mode="execute",
        ),
        arguments={
            "payload": {
                "id": 222,
                "ticketID": 12345,
                "title": title,
                "description": replacement,
                "noteType": 3,
                "publish": 2,
            },
            "expectedDescriptionSha256": expected_hash
            or hashlib.sha256(current.encode("utf-8")).hexdigest(),
            "updateMode": mode,
        },
    )


def test_autonomous_internal_note_update_replaces_only_owned_gpt_insights(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
        note_title="GPT Insights",
        note_description="Initial insight",
    )
    result = _connector(
        transport, _Audit(), autonomy_api_resource_id=29682930
    ).execute(
        _update_connector_request(
            current="Initial insight",
            replacement="Updated insight",
        )
    )
    assert result.data["jasonVerification"]["readbackVerified"] is True
    assert result.data["jasonVerification"]["ticketNoteId"] == 222
    assert transport.note_description == "Updated insight"
    assert [r["method"] for r in transport.requests].count("PATCH") == 1


def test_autonomous_internal_note_update_appends_activity_without_rewriting_history(monkeypatch):
    _enable_mutation(monkeypatch)
    current = "Jason Activity\n\n2026-10-06 07:00 ET - Device check: offline."
    replacement = current + "\n\n2026-10-06 08:00 ET - Recheck: device online."
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
        note_title="Jason Activity",
        note_description=current,
    )
    _connector(
        transport, _Audit(), autonomy_api_resource_id=29682930
    ).execute(
        _update_connector_request(
            current=current,
            replacement=replacement,
            title="Jason Activity",
            mode="append",
        )
    )
    assert transport.note_description == replacement
    assert [r["method"] for r in transport.requests].count("PATCH") == 1


def test_autonomous_internal_note_update_rejects_stale_hash_before_patch(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
        note_title="GPT Insights",
        note_description="Current body",
    )
    with pytest.raises(ConnectorAuthorizationError, match="changed since"):
        _connector(
            transport, _Audit(), autonomy_api_resource_id=29682930
        ).execute(
            _update_connector_request(
                current="Current body",
                replacement="New body",
                expected_hash="0" * 64,
            )
        )
    assert not [r for r in transport.requests if r["method"] == "PATCH"]


def test_autonomous_internal_note_update_rejects_technician_owned_note_before_patch(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
        note_creator_id=77,
        note_title="GPT Insights",
        note_description="Current body",
    )
    with pytest.raises(ConnectorAuthorizationError, match="not created by"):
        _connector(
            transport, _Audit(), autonomy_api_resource_id=29682930
        ).execute(
            _update_connector_request(
                current="Current body", replacement="New body"
            )
        )
    assert not [r for r in transport.requests if r["method"] == "PATCH"]


def test_activity_replace_mode_is_rejected_before_patch(monkeypatch):
    _enable_mutation(monkeypatch)
    transport = _Transport(
        resource_email="jasonrw@teamaot.com",
        resource_id=29682930,
        note_title="Jason Activity",
        note_description="Original activity",
    )
    with pytest.raises(ConnectorAuthorizationError, match="replace mode"):
        _connector(
            transport, _Audit(), autonomy_api_resource_id=29682930
        ).execute(
            _update_connector_request(
                current="Original activity",
                replacement="Rewritten activity",
                title="Jason Activity",
                mode="replace",
            )
        )
    assert not [r for r in transport.requests if r["method"] == "PATCH"]
