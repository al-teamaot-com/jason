from dataclasses import dataclass, field

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.microsoft_graph.resource_connector import (
    MicrosoftGraphResourceConnector,
    PROVIDER_RESOURCE_READ,
    PROVIDER_RESOURCE_SEARCH,
)
from connectors.microsoft_graph.resource_metadata import discover_graph_resources


CSDL = """<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
<edmx:DataServices><Schema Namespace="microsoft.graph" xmlns="http://docs.oasis-open.org/odata/ns/edm">
<EntityType Name="entity"><Key><PropertyRef Name="id"/></Key><Property Name="id" Type="Edm.String" Nullable="false"/></EntityType>
<EntityType Name="futureThing" BaseType="microsoft.graph.entity">
  <Property Name="friendlyName" Type="Edm.String"/>
  <Property Name="enabled" Type="Edm.Boolean"/>
</EntityType>
<EntityContainer Name="GraphService">
  <EntitySet Name="futureThings" EntityType="microsoft.graph.futureThing"/>
</EntityContainer>
</Schema></edmx:DataServices></edmx:Edmx>"""


@dataclass
class Catalogs:
    clients: list[str] = field(default_factory=list)

    def catalog_for_client(self, *, client_id: str, correlation_id: str):
        self.clients.append(client_id)
        return discover_graph_resources(CSDL, source_reference="graph-metadata-test")


@dataclass
class Token:
    access_token: str = "test-token"


@dataclass
class Tokens:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def acquire_for_client(self, *, client_id: str, correlation_id: str):
        self.calls.append((client_id, correlation_id))
        return Token()


@dataclass
class Transport:
    calls: list[dict] = field(default_factory=list)
    response: dict = field(
        default_factory=lambda: {
            "@odata.context": "https://graph.microsoft.test/context",
            "@odata.nextLink": "https://graph.microsoft.test/next?secretish=not-exposed",
            "value": [
                {"id": "1", "friendlyName": "alpha", "enabled": True, "extra": "drop"},
                {"id": "2", "friendlyName": "beta", "enabled": False, "extra": "drop"},
            ],
        }
    )

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@dataclass
class Audit:
    events: list[tuple[str, dict]] = field(default_factory=list)

    def record(self, event_type, context, details):
        self.events.append((event_type, dict(details)))


def context(capability: str, *, client_id: str | None = "client-1"):
    return ConnectorContext(
        correlation_id="corr-1",
        principal_id="person-1",
        organization_id="aot",
        client_id=client_id,
        capability=capability,
        mode="observe",
    )


def test_search_executes_synthetic_metadata_resource_without_entity_specific_code():
    transport = Transport()
    tokens = Tokens()
    catalogs = Catalogs()
    audit = Audit()
    connector = MicrosoftGraphResourceConnector(
        tokens=tokens,
        catalogs=catalogs,
        transport=transport,
        audit=audit,
    )

    result = connector.execute(
        ConnectorRequest(
            context=context(PROVIDER_RESOURCE_SEARCH),
            arguments={
                "provider_resource_handle": "microsoft_graph:futureThings",
                "field_paths": ["id", "friendlyName"],
                "filters": [
                    {"field": "friendlyName", "operator": "contains", "value": "alp"}
                ],
                "top": 10,
            },
        )
    )

    assert result.provider == "microsoft_graph"
    assert result.capability == PROVIDER_RESOURCE_SEARCH
    assert result.data == {
        "items": (
            {"id": "1", "friendlyName": "alpha"},
            {"id": "2", "friendlyName": "beta"},
        ),
        "count": 2,
    }
    assert result.warnings == ("provider_has_additional_results",)
    assert "next" not in repr(result.data).casefold()
    assert "@odata.context" not in repr(result.data)
    assert transport.calls[0]["url"] == "https://graph.microsoft.com/v1.0/futureThings"
    assert transport.calls[0]["params"]["$filter"] == "contains(friendlyName,'alp')"
    assert transport.calls[0]["params"]["$select"] == "id,friendlyName"
    assert tokens.calls == [("client-1", "corr-1")]
    assert catalogs.clients == ["client-1"]
    assert [event[0] for event in audit.events] == [
        "connector.microsoft_graph.resource_read.requested",
        "connector.microsoft_graph.resource_read.completed",
    ]


def test_exact_read_uses_same_generic_connector_and_metadata_handle():
    transport = Transport(
        response={"id": "abc/1", "friendlyName": "one", "enabled": True, "extra": "drop"}
    )
    connector = MicrosoftGraphResourceConnector(
        tokens=Tokens(),
        catalogs=Catalogs(),
        transport=transport,
        audit=Audit(),
    )

    result = connector.execute(
        ConnectorRequest(
            context=context(PROVIDER_RESOURCE_READ),
            arguments={
                "provider_resource_handle": "microsoft_graph:futureThings",
                "resource_id": "abc/1",
                "field_paths": ["id", "enabled"],
            },
        )
    )

    assert result.data == {"item": {"id": "abc/1", "enabled": True}}
    assert transport.calls[0]["url"].endswith("/futureThings/abc%2F1")


def test_missing_client_boundary_fails_before_catalog_token_or_transport():
    transport = Transport()
    tokens = Tokens()
    catalogs = Catalogs()
    connector = MicrosoftGraphResourceConnector(
        tokens=tokens,
        catalogs=catalogs,
        transport=transport,
        audit=Audit(),
    )

    with pytest.raises(PermissionError, match="client boundary"):
        connector.execute(
            ConnectorRequest(
                context=context(PROVIDER_RESOURCE_SEARCH, client_id=None),
                arguments={
                    "provider_resource_handle": "microsoft_graph:futureThings",
                    "field_paths": ["id"],
                },
            )
        )

    assert catalogs.clients == []
    assert tokens.calls == []
    assert transport.calls == []


def test_unknown_resource_or_field_fails_before_token_and_transport():
    transport = Transport()
    tokens = Tokens()
    connector = MicrosoftGraphResourceConnector(
        tokens=tokens,
        catalogs=Catalogs(),
        transport=transport,
        audit=Audit(),
    )

    with pytest.raises(Exception, match="unknown governed"):
        connector.execute(
            ConnectorRequest(
                context=context(PROVIDER_RESOURCE_SEARCH),
                arguments={
                    "provider_resource_handle": "microsoft_graph:notReal",
                    "field_paths": ["id"],
                },
            )
        )

    with pytest.raises(Exception, match="outside discovered metadata"):
        connector.execute(
            ConnectorRequest(
                context=context(PROVIDER_RESOURCE_SEARCH),
                arguments={
                    "provider_resource_handle": "microsoft_graph:futureThings",
                    "field_paths": ["id", "madeUpField"],
                },
            )
        )

    assert tokens.calls == []
    assert transport.calls == []


def test_non_observe_mode_is_denied_by_connector_contract():
    connector = MicrosoftGraphResourceConnector(
        tokens=Tokens(),
        catalogs=Catalogs(),
        transport=Transport(),
        audit=Audit(),
    )
    bad_context = ConnectorContext(
        correlation_id="corr-1",
        principal_id="person-1",
        organization_id="aot",
        client_id="client-1",
        capability=PROVIDER_RESOURCE_SEARCH,
        mode="execute",
    )
    with pytest.raises(PermissionError, match="read-only"):
        connector.execute(
            ConnectorRequest(
                context=bad_context,
                arguments={
                    "provider_resource_handle": "microsoft_graph:futureThings",
                    "field_paths": ["id"],
                },
            )
        )
