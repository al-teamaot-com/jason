from __future__ import annotations

from dataclasses import dataclass

import pytest

from connectors.core.contracts import (
    ConnectorAuthorizationError,
    ConnectorContext,
    ConnectorRequest,
)
from connectors.microsoft_graph.directory_connector import MicrosoftGraphDirectoryConnector
from connectors.microsoft_graph.user_directory import MicrosoftGraphUserDirectoryReader


class Tokens:
    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str:
        assert microsoft_tenant_id == "tenant-aot"
        return "synthetic-token"


class Transport:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        url = kwargs["url"]
        if url.endswith("/users"):
            return {
                "value": [
                    {
                        "id": "object-user-1",
                        "displayName": "Example User",
                        "mail": "user@example.com",
                        "userPrincipalName": "user@example.com",
                        "accountEnabled": True,
                    }
                ]
            }
        return {
            "id": "object-user-1",
            "displayName": "Example User",
            "mail": "user@example.com",
            "userPrincipalName": "user@example.com",
            "accountEnabled": True,
        }


@dataclass(frozen=True)
class Binding:
    jason_identity_id: str = "person-al"
    microsoft_tenant_id: str = "tenant-aot"
    microsoft_object_id: str = "object-al"
    status: str = "active"


class Bindings:
    def __init__(self, binding=Binding()):
        self.binding = binding

    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        if self.binding is None or self.binding.jason_identity_id != jason_identity_id:
            return None
        return self.binding


class Audit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append(event_type)


def context(capability: str) -> ConnectorContext:
    return ConnectorContext(
        correlation_id="corr-entra",
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability=capability,
        mode="observe",
    )


def connector(*, bindings=Bindings()):
    transport = Transport()
    audit = Audit()
    return (
        MicrosoftGraphDirectoryConnector(
            directory=MicrosoftGraphUserDirectoryReader(
                tokens=Tokens(),
                transport=transport,
                sleeper=lambda _: None,
            ),
            bindings=bindings,
            audit=audit,
        ),
        transport,
        audit,
    )


def test_exact_email_search_is_tenant_bound_bounded_and_read_only():
    subject, transport, audit = connector()

    result = subject.execute(
        ConnectorRequest(
            context=context("microsoft_graph.user.search"),
            arguments={"email": "user@example.com", "page_size": 5},
        )
    )

    assert result.provider == "microsoft_graph"
    assert result.capability == "microsoft_graph.user.search"
    assert result.data["count"] == 1
    assert result.data["items"][0]["id"] == "object-user-1"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://graph.microsoft.com/v1.0/users"
    assert call["params"]["$filter"] == "mail eq 'user@example.com'"
    assert call["params"]["$top"] == 5
    assert audit.events == ["connector.requested", "connector.completed"]


def test_exact_user_read_uses_only_bound_tenant_and_object_id():
    subject, transport, _audit = connector()

    result = subject.execute(
        ConnectorRequest(
            context=context("microsoft_graph.user.get"),
            arguments={"resource_id": "object-user-1"},
        )
    )

    assert result.data["item"]["userPrincipalName"] == "user@example.com"
    assert len(transport.calls) == 1
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["url"].endswith("/users/object-user-1")


def test_search_rejects_missing_or_ambiguous_selector_before_graph_io():
    subject, transport, _audit = connector()

    for arguments in (
        {},
        {"email": "user@example.com", "display_name": "Example User"},
    ):
        with pytest.raises(ValueError, match="exact selector"):
            subject.execute(
                ConnectorRequest(
                    context=context("microsoft_graph.user.search"),
                    arguments=arguments,
                )
            )

    assert transport.calls == []


def test_missing_trusted_binding_fails_before_graph_io():
    subject, transport, _audit = connector(bindings=Bindings(None))

    with pytest.raises(
        ConnectorAuthorizationError,
        match="Microsoft identity binding",
    ):
        subject.execute(
            ConnectorRequest(
                context=context("microsoft_graph.user.search"),
                arguments={"email": "user@example.com"},
            )
        )

    assert transport.calls == []


def test_graph_search_escapes_odata_string_and_is_bounded():
    subject, transport, _audit = connector()

    subject.execute(
        ConnectorRequest(
            context=context("microsoft_graph.user.search"),
            arguments={"display_name": "O'Brien", "page_size": 1},
        )
    )

    assert transport.calls[0]["params"]["$filter"] == "displayName eq 'O''Brien'"
    assert transport.calls[0]["params"]["$top"] == 1
