from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import pytest

from connectors.microsoft_graph.platform import (
    MicrosoftCloudRequest,
    MicrosoftRequestPolicyError,
    build_governed_request,
)
from connectors.microsoft_graph.resource_metadata import (
    MicrosoftGraphMetadataError,
    discover_graph_resources,
)
from connectors.microsoft_graph.resource_read import (
    MicrosoftGraphFilter,
    MicrosoftGraphOrder,
    MicrosoftGraphReadCompiler,
    MicrosoftGraphReadIntent,
    MicrosoftGraphResourceReadError,
    MicrosoftGraphResourceReader,
)
from connectors.microsoft_graph.service_catalog import MicrosoftOperationMode, MicrosoftService


CSDL = """<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
<edmx:DataServices><Schema Namespace="microsoft.graph" xmlns="http://docs.oasis-open.org/odata/ns/edm">
<EntityType Name="entity"><Key><PropertyRef Name="id"/></Key><Property Name="id" Type="Edm.String" Nullable="false"/></EntityType>
<EntityType Name="user" BaseType="microsoft.graph.entity">
  <Property Name="displayName" Type="Edm.String"/>
  <Property Name="mail" Type="Edm.String"/>
  <Property Name="userPrincipalName" Type="Edm.String"/>
  <Property Name="accountEnabled" Type="Edm.Boolean"/>
</EntityType>
<EntityType Name="device" BaseType="microsoft.graph.entity">
  <Property Name="displayName" Type="Edm.String"/>
  <Property Name="operatingSystem" Type="Edm.String"/>
</EntityType>
<EntityContainer Name="GraphService">
  <EntitySet Name="users" EntityType="microsoft.graph.user"/>
  <EntitySet Name="devices" EntityType="microsoft.graph.device"/>
</EntityContainer>
</Schema></edmx:DataServices></edmx:Edmx>"""


def compiler():
    catalog = discover_graph_resources(CSDL, source_reference="graph-metadata")
    return MicrosoftGraphReadCompiler(catalog=catalog)


def test_compiles_collection_read_from_discovered_resource_and_fields():
    compiled = compiler().compile(
        intent=MicrosoftGraphReadIntent(
            resource_handle="microsoft_graph:users",
            select=("id", "displayName", "mail", "userPrincipalName"),
            filters=(MicrosoftGraphFilter("displayName", "startswith", "Al"),),
            order_by=(MicrosoftGraphOrder("displayName", "asc"),),
            top=25,
        ),
        permission_profile_name="directory-read",
    )

    parsed = urlsplit(compiled.request.url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "graph.microsoft.com"
    assert parsed.path == "/v1.0/users"
    assert query["$select"] == ["id,displayName,mail,userPrincipalName"]
    assert query["$filter"] == ["startswith(displayName,'Al')"]
    assert query["$orderby"] == ["displayName asc"]
    assert query["$top"] == ["25"]
    assert compiled.request.method == "GET"
    assert compiled.request.mode is MicrosoftOperationMode.READ


def test_exact_item_read_uses_discovered_collection_path_and_escaped_identifier():
    compiled = compiler().compile(
        intent=MicrosoftGraphReadIntent(
            resource_handle="microsoft_graph:devices",
            resource_id="device/id value",
            select=("id", "displayName", "operatingSystem"),
        ),
        permission_profile_name="directory-read",
    )
    parsed = urlsplit(compiled.request.url)
    assert parsed.path == "/v1.0/devices/device%2Fid%20value"
    assert parse_qs(parsed.query)["$select"] == ["id,displayName,operatingSystem"]
    assert "$top" not in parse_qs(parsed.query)


def test_unknown_resource_or_field_cannot_be_used_as_an_escape_hatch():
    with pytest.raises(MicrosoftGraphMetadataError, match="unknown governed"):
        compiler().compile(
            intent=MicrosoftGraphReadIntent(
                resource_handle="microsoft_graph:/me/messages",
                select=("id",),
            ),
            permission_profile_name="directory-read",
        )

    with pytest.raises(MicrosoftGraphResourceReadError, match="outside discovered metadata"):
        compiler().compile(
            intent=MicrosoftGraphReadIntent(
                resource_handle="microsoft_graph:users",
                select=("id", "passwordProfile"),
            ),
            permission_profile_name="directory-read",
        )


def test_filter_values_are_literals_not_raw_odata_fragments():
    attempted_injection = "O'Brien') or accountEnabled eq false or ('x' eq 'x"
    compiled = compiler().compile(
        intent=MicrosoftGraphReadIntent(
            resource_handle="microsoft_graph:users",
            select=("id", "displayName"),
            filters=(
                MicrosoftGraphFilter(
                    "displayName",
                    "contains",
                    attempted_injection,
                ),
            ),
            top=10,
        ),
        permission_profile_name="directory-read",
    )
    value = parse_qs(urlsplit(compiled.request.url).query)["$filter"][0]
    assert value == (
        "contains(displayName,'O''Brien'') or accountEnabled eq false "
        "or (''x'' eq ''x')"
    )
    assert value.count("'") == 12


def test_raw_query_options_and_mutating_read_requests_fail_closed():
    with pytest.raises(ValueError, match="Unsupported Microsoft query option"):
        MicrosoftCloudRequest(
            service=MicrosoftService.GRAPH,
            method="GET",
            path="/users",
            permission_profile_name="directory-read",
            query={"evil": "value"},
        )

    with pytest.raises(MicrosoftRequestPolicyError, match="Read mode permits only"):
        build_governed_request(
            MicrosoftCloudRequest(
                service=MicrosoftService.GRAPH,
                method="POST",
                path="/users",
                permission_profile_name="directory-read",
                mode=MicrosoftOperationMode.READ,
            )
        )


@dataclass
class Tokens:
    tenant_seen: str | None = None

    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str:
        self.tenant_seen = microsoft_tenant_id
        return "test-token"


@dataclass
class Transport:
    call: dict | None = None

    def request(self, **kwargs):
        self.call = kwargs
        return {"value": [{"id": "u1", "mail": "user@example.test"}]}


def test_reader_executes_only_the_compiled_governed_request():
    tokens = Tokens()
    transport = Transport()
    reader = MicrosoftGraphResourceReader(
        compiler=compiler(),
        tokens=tokens,
        transport=transport,
    )

    response = reader.read(
        microsoft_tenant_id="tenant-1",
        intent=MicrosoftGraphReadIntent(
            resource_handle="microsoft_graph:users",
            select=("id", "mail"),
            filters=(MicrosoftGraphFilter("mail", "eq", "user@example.test"),),
            top=5,
        ),
        permission_profile_name="directory-read",
    )

    assert response["value"][0]["mail"] == "user@example.test"
    assert tokens.tenant_seen == "tenant-1"
    assert transport.call["method"] == "GET"
    assert transport.call["url"] == "https://graph.microsoft.com/v1.0/users"
    assert transport.call["params"]["$select"] == "id,mail"
    assert transport.call["params"]["$filter"] == "mail eq 'user@example.test'"
    assert transport.call["headers"]["Authorization"] == "Bearer test-token"
