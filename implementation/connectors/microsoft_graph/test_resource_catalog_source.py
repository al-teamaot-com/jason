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


def test_catalog_source_discovers_unprogrammed_resource_without_tenant_data_access():
    transport = TextTransport()
    source = MicrosoftGraphMetadataCatalogSource(transport=transport)

    catalog = source.catalog(correlation_id="corr-1")

    resource = catalog.get("microsoft_graph:newProviderObjects")
    assert resource.resource_type == "newProviderObject"
    assert resource.field_names == ("id", "label")
    assert transport.calls[0]["url"] == "https://graph.microsoft.com/v1.0/$metadata"
    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["headers"] == {"Accept": "application/xml"}
    assert "Authorization" not in transport.calls[0]["headers"]


def test_provider_global_metadata_cache_is_shared_and_ttl_bounded():
    transport = TextTransport()
    clock = Clock()
    source = MicrosoftGraphMetadataCatalogSource(
        transport=transport,
        cache_ttl_seconds=60,
        clock=clock,
    )

    first = source.catalog(correlation_id="corr-1")
    second = source.catalog_for_client(client_id="client-1", correlation_id="corr-2")
    third = source.provider_catalog(correlation_id="corr-3")
    assert first is second
    assert third.provider_id == "microsoft_graph"
    assert len(transport.calls) == 1

    clock.now += 61
    source.catalog(correlation_id="corr-4")
    assert len(transport.calls) == 2


def test_client_scoped_catalog_entry_point_still_requires_a_named_client():
    transport = TextTransport()
    source = MicrosoftGraphMetadataCatalogSource(transport=transport)

    with pytest.raises(ConnectorAuthorizationError, match="client boundary"):
        source.catalog_for_client(client_id="", correlation_id="corr-1")

    assert transport.calls == []


def test_catalog_source_does_not_accept_a_conversation_supplied_metadata_url():
    source = MicrosoftGraphMetadataCatalogSource(transport=TextTransport())
    assert source.provider_id == "microsoft_graph"
    assert not hasattr(source, "metadata_url")
    assert not hasattr(source, "url")
