from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pytest

from connectors.autotask.mutation_connector import AUTOTASK_MUTATION_ENABLED_ENV
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from jason_runtime.autotask_managed_note_update import (
    AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER,
    AutotaskManagedNoteUpdateConnector,
    AutotaskManagedNoteUpdateVerificationError,
    register_autotask_managed_note_update_runtime_foundation,
)
from jason_runtime.autotask_internal_note import (
    AUTOTASK_INTERNAL_NOTE_PROFILE,
    AUTOTASK_INTERNAL_NOTE_PROFILE_ENV,
)
from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderLifecycle,
)


class _Secrets:
    def resolve(self, logical_name, context):
        del context
        assert logical_name == "autotask.write"
        return {
            "username": "write@example.invalid",
            "secret": "synthetic-secret",
            "integration_code": "synthetic-code",
        }


class _Audit:
    def __init__(self):
        self.events: list[tuple[str, dict[str, Any]]] = []

    def record(self, event_type, context, details):
        del context
        self.events.append((str(event_type), dict(details)))


@dataclass(frozen=True)
class _Binding:
    jason_identity_id: str = "person-al"
    email_address: str = "al@example.invalid"


class _Bindings:
    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        if jason_identity_id == "person-al":
            return _Binding()
        return None


class _Transport:
    def __init__(
        self,
        *,
        title="GPT Insights",
        description="old body",
        creator=29682930,
        note_type=3,
        publish=2,
    ):
        self.note = {
            "id": 456,
            "ticketID": 123,
            "title": title,
            "description": description,
            "noteType": note_type,
            "publish": publish,
            "creatorResourceID": creator,
            "impersonatorCreatorResourceID": None,
        }
        self.requests: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
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
        if url.endswith("/v1.0/zoneInformation"):
            return {"url": "https://webservices3.autotask.net/atservicesrest/"}
        if url.endswith("/V1.0/TicketNotes/entityInformation"):
            return {"userAccessForCreate": 1, "userAccessForUpdate": 1}
        if url.endswith("/V1.0/Tickets/123/Notes") and method == "GET":
            return {"items": [dict(self.note)]}
        if url.endswith("/V1.0/Tickets/123/Notes") and method == "PATCH":
            assert isinstance(json, Mapping)
            self.note.update(dict(json))
            return {"itemId": 456}
        raise AssertionError(f"unexpected transport request: {method} {url}")


def _request(*, title="GPT Insights", description="new body"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-managed-note",
            principal_id="jason-autonomy-worker",
            organization_id="aot",
            client_id=None,
            capability="autotask.ticket.note.update",
            mode="execute",
        ),
        arguments={
            "payload": {
                "ticketID": 123,
                "id": 456,
                "title": title,
                "description": description,
                "noteType": 3,
                "publish": 2,
            }
        },
    )


def _connector(transport, audit=None):
    return AutotaskManagedNoteUpdateConnector(
        secrets=_Secrets(),
        transport=transport,
        audit=audit or _Audit(),
        bindings=_Bindings(),
        autonomy_api_resource_id=29682930,
    )


@pytest.fixture(autouse=True)
def _enable_mutation(monkeypatch):
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")


def test_gpt_insights_update_requires_owner_readback_and_records_revision():
    transport = _Transport()
    audit = _Audit()
    result = _connector(transport, audit).execute(
        _request(description="new body")
    )

    assert transport.note["description"] == "new body"
    assert sum(r["method"] == "PATCH" for r in transport.requests) == 1
    verification = result.data["jasonVerification"]
    assert verification["readbackVerified"] is True
    assert verification["ticketNoteId"] == 456
    revisions = [
        details
        for event, details in audit.events
        if event == "connector.managed_note.revision"
    ]
    assert len(revisions) == 1
    assert revisions[0]["prior_body"] == "old body"
    assert revisions[0]["revised_body"] == "new body"
    assert revisions[0]["prior_sha256"] != revisions[0]["revised_sha256"]


def test_jason_activity_update_must_append_prior_body():
    transport = _Transport(title="Jason Activity", description="first entry")
    result = _connector(transport).execute(
        _request(
            title="Jason Activity",
            description="first entry\n\nsecond entry",
        )
    )
    assert result.data["jasonVerification"]["readbackVerified"] is True

    transport = _Transport(title="Jason Activity", description="first entry")
    with pytest.raises(
        PermissionError,
        match="AUTOTASK_JASON_ACTIVITY_UPDATE_MUST_BE_APPEND_ONLY",
    ):
        _connector(transport).execute(
            _request(title="Jason Activity", description="replacement")
        )
    assert not any(r["method"] == "PATCH" for r in transport.requests)


def test_update_rejects_note_not_created_by_jason_before_patch():
    transport = _Transport(creator=1234)
    with pytest.raises(
        AutotaskManagedNoteUpdateVerificationError,
        match="creator does not match",
    ):
        _connector(transport).execute(_request())
    assert not any(r["method"] == "PATCH" for r in transport.requests)


def test_update_rejects_client_visible_or_unmanaged_title_before_patch():
    transport = _Transport()
    bad_visibility = _request()
    bad_visibility = ConnectorRequest(
        context=bad_visibility.context,
        arguments={
            "payload": {
                **bad_visibility.arguments["payload"],
                "publish": 1,
            }
        },
    )
    with pytest.raises(PermissionError, match="MUST_REMAIN_INTERNAL"):
        _connector(transport).execute(bad_visibility)
    assert not any(r["method"] == "PATCH" for r in transport.requests)

    transport = _Transport(title="Technician Notes")
    with pytest.raises(PermissionError, match="TITLE_NOT_ALLOWED"):
        _connector(transport).execute(
            _request(title="Technician Notes")
        )
    assert not any(r["method"] == "PATCH" for r in transport.requests)



def test_managed_note_update_foundation_activates_under_existing_internal_note_profile(
    monkeypatch,
):
    monkeypatch.setenv(AUTOTASK_INTERNAL_NOTE_PROFILE_ENV, AUTOTASK_INTERNAL_NOTE_PROFILE)
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    from datetime import datetime, timezone

    state = register_autotask_managed_note_update_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert state.enabled is True
    assert state.capability_names == ("service.ticket.note.update",)
    capability = capabilities.get(
        capability_name="service.ticket.note.update",
        version="1.0",
    )
    assert capability.lifecycle_status is CapabilityLifecycle.ACTIVE
    provider = providers.get(AUTOTASK_MANAGED_NOTE_UPDATE_PROVIDER)
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE


class _PrePatchDriftTransport(_Transport):
    def __init__(self):
        super().__init__(description="old body")
        self.note_reads = 0

    def request(self, **kwargs):
        method = kwargs.get("method")
        url = kwargs.get("url", "")
        if method == "GET" and str(url).endswith("/V1.0/Tickets/123/Notes"):
            self.note_reads += 1
            if self.note_reads == 2:
                self.note["description"] = "concurrent technician edit"
        return super().request(**kwargs)


def test_update_rejects_note_changed_after_plan_preparation_before_patch():
    transport = _PrePatchDriftTransport()
    connector = _connector(transport)
    with pytest.raises(
        AutotaskManagedNoteUpdateVerificationError,
        match="changed after execution plan preparation",
    ):
        connector.execute(_request(description="new body"))
    assert transport.note_reads == 2
    assert not any(r["method"] == "PATCH" for r in transport.requests)
