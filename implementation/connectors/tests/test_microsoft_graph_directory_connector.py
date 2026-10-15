from __future__ import annotations

from dataclasses import dataclass

from orchestrator.provider_health_canary_policy import (
    PROVIDER_HEALTH_CANARY_PRINCIPAL,
    PROVIDER_HEALTH_CANARY_SENTINEL,
    expected_canary_arguments,
)

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


def connector(*, bindings=Bindings(), canary_boundaries=None):
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
            canary_boundaries=canary_boundaries,
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



@dataclass(frozen=True)
class CanaryBoundary:
    client_id: str = "client-aot-internal"
    provider: str = "microsoft_graph"
    status: str = "validated"
    external_tenant_id: str = "tenant-aot"


class CanaryBoundaries:
    def __init__(self, boundary=CanaryBoundary()):
        self.boundary = boundary

    def find_active_for_client(self, *, client_id, provider):
        if self.boundary is None:
            return None
        if client_id == "client-aot-internal" and provider == "microsoft_graph":
            return self.boundary
        return None


def canary_request(*, client_id="client-aot-internal", capability="microsoft_graph.user.search", arguments=None, principal_id=PROVIDER_HEALTH_CANARY_PRINCIPAL):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-canary-test",
            principal_id=principal_id,
            organization_id="aot",
            client_id=client_id,
            capability=capability,
            mode="observe",
        ),
        arguments=(
            dict(expected_canary_arguments("identity.user.search"))
            if arguments is None else arguments
        ),
    )


def test_graph_canary_exact_sentinel_uses_validated_client_tenant_without_human_identity():
    subject, transport, audit = connector(
        bindings=Bindings(binding=None), canary_boundaries=CanaryBoundaries()
    )
    # The synthetic nonexistent selector must yield no user data. The
    # information-authorizer separately refuses to release nonempty output.
    transport.request = lambda **kwargs: {"value": []}
    result = subject.execute(canary_request())
    assert result.data == {"items": [], "count": 0}
    assert audit.events == ["connector.requested", "connector.completed"]


@pytest.mark.parametrize("request", [
    canary_request(client_id="other-client"),
    canary_request(capability="microsoft_graph.user.get", arguments={"resource_id": "object-user-1"}),
    canary_request(arguments={"email": "user@example.com", "page_size": 1}),
    canary_request(arguments={"display_name": PROVIDER_HEALTH_CANARY_SENTINEL, "page_size": 2}),
])
def test_graph_canary_denies_all_non_sentinel_client_or_capability(request):
    subject, transport, _audit = connector(
        bindings=Bindings(binding=None), canary_boundaries=CanaryBoundaries()
    )
    with pytest.raises(ConnectorAuthorizationError):
        subject.execute(request)
    assert transport.calls == []


def test_graph_canary_denies_missing_unvalidated_tenant_boundary():
    for boundaries in (None, CanaryBoundaries(None), CanaryBoundaries(CanaryBoundary(status="pending"))):
        subject, transport, _audit = connector(
            bindings=Bindings(binding=None), canary_boundaries=boundaries
        )
        with pytest.raises(ConnectorAuthorizationError):
            subject.execute(canary_request())
        assert transport.calls == []
