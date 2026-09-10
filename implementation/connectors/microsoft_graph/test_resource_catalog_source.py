from dataclasses import dataclass, field

import pytest

from connectors.core.contracts import ConnectorAuthorizationError
from connectors.microsoft_graph.resource_catalog_source import (
    MicrosoftGraphMetadataCatalogSource,
)


CSDL = """<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
<edmx:DataServices><Schema Namespace="microsoft.graph" xmlns="http://docs.oasis-open.org/odata/ns/edm">
<EntityType Name="entity"><Key><PropertyRef Name="id"/></Key><Property Name="id" Type="Edm.String" Nullable="false"/></EntityType>
<EntityType Name="newProviderObject" BaseType="microsoft.graph.entity"><Property Name="label" Type="Edm.String"/></EntityType>
<EntityContainer Name="GraphService"><EntitySet Name="newProviderObjects" EntityType="microsoft.graph.newProviderObject"/></EntityContainer>
</Schema></edmx:DataServices></edmx:Edmx>"""


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
class TextTransport:
    calls: list[dict] = field(default_factory=list)

    def request_text(self, **kwargs):
        self.calls.append(kwargs)
        return CSDL


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_catalog_source_discovers_unprogrammed_resource_from_provider_metadata():
    tokens = Tokens()
    transport = TextTransport()
    clock = Clock()
    source = MicrosoftGraphMetadataCatalogSource(
        tokens=tokens,
        transport=transport,
        cache_ttl_seconds=60,
        clock=clock,
    )

    catalog = source.catalog_for_client(client_id="client-1", correlation_id="corr-1")

    resource = catalog.get("microsoft_graph:newProviderObjects")
    assert resource.resource_type == "newProviderObject"
    assert resource.field_names == ("id", "label")
    assert transport.calls[0]["url"] == "https://graph.microsoft.com/v1.0/$metadata"
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["headers"]["Accept"] == "application/xml"
    assert transport.calls[0]["headers"]["Authorization"].startswith("Bearer ")
    assert tokens.calls == [("client-1", "corr-1")]


def test_catalog_source_cache_is_client_scoped_and_bounded_by_ttl():
    tokens = Tokens()
    transport = TextTransport()
    clock = Clock()
    source = MicrosoftGraphMetadataCatalogSource(
        tokens=tokens,
        transport=transport,
        cache_ttl_seconds=60,
        clock=clock,
    )

    first = source.catalog_for_client(client_id="client-1", correlation_id="corr-1")
    second = source.catalog_for_client(client_id="client-1", correlation_id="corr-2")
    assert first is second
    assert len(tokens.calls) == 1
    assert len(transport.calls) == 1

    source.catalog_for_client(client_id="client-2", correlation_id="corr-3")
    assert len(tokens.calls) == 2
    assert len(transport.calls) == 2

    clock.now += 61
    source.catalog_for_client(client_id="client-1", correlation_id="corr-4")
    assert len(tokens.calls) == 3
    assert len(transport.calls) == 3


def test_catalog_source_requires_client_boundary_before_token_or_transport():
    tokens = Tokens()
    transport = TextTransport()
    source = MicrosoftGraphMetadataCatalogSource(tokens=tokens, transport=transport)

    with pytest.raises(ConnectorAuthorizationError, match="client boundary"):
        source.catalog_for_client(client_id="", correlation_id="corr-1")

    assert tokens.calls == []
    assert transport.calls == []


def test_catalog_source_does_not_accept_a_conversation_supplied_metadata_url():
    source = MicrosoftGraphMetadataCatalogSource(tokens=Tokens(), transport=TextTransport())
    assert not hasattr(source, "metadata_url")
    assert not hasattr(source, "url")
