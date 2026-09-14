import pytest

from connectors.microsoft_graph.resource_metadata import (
    MicrosoftGraphMetadataError,
    discover_graph_resources,
)


CSDL = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="microsoft.graph" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityType Name="entity">
        <Key><PropertyRef Name="id" /></Key>
        <Property Name="id" Type="Edm.String" Nullable="false" />
      </EntityType>
      <EntityType Name="directoryObject" BaseType="microsoft.graph.entity">
        <Property Name="deletedDateTime" Type="Edm.DateTimeOffset" />
      </EntityType>
      <EntityType Name="user" BaseType="microsoft.graph.directoryObject">
        <Property Name="displayName" Type="Edm.String" />
        <Property Name="mail" Type="Edm.String" />
        <Property Name="userPrincipalName" Type="Edm.String" />
        <Property Name="businessPhones" Type="Collection(Edm.String)" Nullable="false" />
        <NavigationProperty Name="manager" Type="microsoft.graph.directoryObject" />
      </EntityType>
      <EntityType Name="group" BaseType="microsoft.graph.directoryObject">
        <Property Name="displayName" Type="Edm.String" />
        <Property Name="mail" Type="Edm.String" />
      </EntityType>
      <EntityContainer Name="GraphService">
        <EntitySet Name="users" EntityType="microsoft.graph.user" />
        <EntitySet Name="groups" EntityType="microsoft.graph.group" />
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""


def test_discovers_entity_sets_and_inherited_fields_without_entity_hardcoding():
    catalog = discover_graph_resources(
        CSDL,
        source_reference="https://graph.microsoft.com/v1.0/$metadata",
    )

    assert [item.entity_set for item in catalog.resources] == ["groups", "users"]

    users = catalog.get("microsoft_graph:users")
    assert users.resource_type == "user"
    assert users.collection_path == "/users"
    assert users.key_fields == ("id",)
    assert set(users.field_names) == {
        "id",
        "deletedDateTime",
        "displayName",
        "mail",
        "userPrincipalName",
        "businessPhones",
    }
    assert "manager" not in users.field_names
    business_phones = next(field for field in users.fields if field.name == "businessPhones")
    assert business_phones.collection is True
    assert business_phones.type_name == "Edm.String"


def test_model_context_is_structural_and_does_not_include_provider_credentials():
    catalog = discover_graph_resources(CSDL, source_reference="graph-metadata")
    context = catalog.model_context()

    assert context[0]["resource_handle"] == "microsoft_graph:groups"
    assert context[1]["resource_type"] == "user"
    assert "token" not in repr(context).casefold()
    assert "credential" not in repr(context).casefold()


def test_provider_neutral_catalog_is_derived_from_metadata_not_a_fixed_entity_list():
    novel = CSDL.replace(
        '<EntityContainer Name="GraphService">',
        '''<EntityType Name="futureThing" BaseType="microsoft.graph.entity">
        <Property Name="friendlyName" Type="Edm.String" />
        <Property Name="enabled" Type="Edm.Boolean" Nullable="false" />
      </EntityType>
      <EntityContainer Name="GraphService">''',
    ).replace(
        '<EntitySet Name="users" EntityType="microsoft.graph.user" />',
        '''<EntitySet Name="users" EntityType="microsoft.graph.user" />
        <EntitySet Name="futureThings" EntityType="microsoft.graph.futureThing" />''',
    )

    graph_catalog = discover_graph_resources(novel, source_reference="graph-metadata-vnext")
    provider_catalog = graph_catalog.provider_resource_catalog()

    future = provider_catalog.get("microsoft_graph:futureThings")
    assert future.provider_id == "microsoft_graph"
    assert future.resource_type == "futureThing"
    assert future.operations == ("search", "read")
    assert future.collection_supported is True
    assert future.selector_keys == ("id",)
    assert {field.path for field in future.fields} == {"id", "friendlyName", "enabled"}
    assert next(field for field in future.fields if field.path == "enabled").value_type == "boolean"


def test_unknown_resource_handle_fails_closed():
    catalog = discover_graph_resources(CSDL, source_reference="graph-metadata")
    with pytest.raises(MicrosoftGraphMetadataError, match="unknown governed"):
        catalog.get("microsoft_graph:not-a-real-resource")


def test_invalid_or_unbounded_metadata_is_rejected():
    with pytest.raises(MicrosoftGraphMetadataError, match="valid XML"):
        discover_graph_resources("not xml", source_reference="graph-metadata")

    with pytest.raises(MicrosoftGraphMetadataError, match="empty or exceeds"):
        discover_graph_resources(b"", source_reference="graph-metadata")


def test_unsafe_entity_set_from_metadata_is_rejected():
    unsafe = CSDL.replace('Name="users" EntityType=', 'Name="../users" EntityType=')
    with pytest.raises(MicrosoftGraphMetadataError, match="unsafe Graph entity-set"):
        discover_graph_resources(unsafe, source_reference="graph-metadata")
