import pytest

from orchestrator.open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)
from orchestrator.open_world_semantic_mapping import (
    OpenWorldSemanticMapper,
)


def catalog():
    return OpenWorldResourceCatalog(
        resources=(
            DiscoveredResourceSchema(
                provider_id="p1",
                capability_name="synthetic.read",
                resource_type="synthetic_resource",
                operation="read",
                collection_supported=False,
                selector_keys=("id",),
                fields=(
                    DiscoveredField(
                        name="value",
                        path="unknown_branch.value",
                        value_type="number",
                    ),
                ),
            ),
        )
    )


class FakeClient:
    def __init__(
        self,
        resource_handle,
    ):
        self.resource_handle = (
            resource_handle
        )

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens,
    ):
        del system
        del user
        del schema
        del max_output_tokens

        return {
            "information_request": True,
            "bindings": [
                {
                    "resource_handle": (
                        self.resource_handle
                    ),
                    "field_path": (
                        "unknown_branch.value"
                    ),
                    "semantic_role": (
                        "requested_measure"
                    ),
                }
            ],
        }


class NonInformationClient:
    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens,
    ):
        del system
        del user
        del schema
        del max_output_tokens

        return {
            "information_request": False,
            "bindings": [],
        }


class InventingClient:
    def __init__(
        self,
        resource_handle,
    ):
        self.resource_handle = (
            resource_handle
        )

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens,
    ):
        del system
        del user
        del schema
        del max_output_tokens

        return {
            "information_request": True,
            "bindings": [
                {
                    "resource_handle": (
                        self.resource_handle
                    ),
                    "field_path": (
                        "field_that_does_not_exist"
                    ),
                    "semantic_role": (
                        "requested_measure"
                    ),
                }
            ],
        }


class WrongHandleClient:
    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens,
    ):
        del system
        del user
        del schema
        del max_output_tokens

        return {
            "information_request": True,
            "bindings": [
                {
                    "resource_handle": (
                        "resource_not_real"
                    ),
                    "field_path": (
                        "unknown_branch.value"
                    ),
                    "semantic_role": (
                        "requested_measure"
                    ),
                }
            ],
        }


def test_mapper_accepts_discovered_field_without_canonical_fact():
    value = catalog()

    result = OpenWorldSemanticMapper(
        client=FakeClient(
            resource_handle=(
                value.resources[0]
                .resource_handle
            )
        )
    ).map(
        human_text="unseen request",
        catalog=value,
    )

    assert (
        result.information_request
        is True
    )

    assert (
        result.bindings[0]
        .resource_handle
        == value.resources[0]
        .resource_handle
    )

    assert (
        result.bindings[0]
        .field_path
        == "unknown_branch.value"
    )


def test_non_information_request_has_no_bindings():
    value = catalog()

    result = OpenWorldSemanticMapper(
        client=NonInformationClient()
    ).map(
        human_text="unseen text",
        catalog=value,
    )

    assert (
        result.information_request
        is False
    )

    assert result.bindings == ()



def test_mapper_discards_unknown_early_field_binding():
    value = catalog()

    result = OpenWorldSemanticMapper(
        client=InventingClient(
            resource_handle=(
                value.resources[0]
                .resource_handle
            )
        )
    ).map(
        human_text="unseen operational information request",
        catalog=value,
    )

    assert result.information_request is True
    assert result.bindings == ()


def test_mapper_discards_unknown_early_resource_binding():
    value = catalog()

    result = OpenWorldSemanticMapper(
        client=WrongHandleClient()
    ).map(
        human_text="another unseen operational information request",
        catalog=value,
    )

    assert result.information_request is True
    assert result.bindings == ()

def test_model_context_hides_provider_and_capability_identity():
    value = catalog()

    context = value.model_context()

    text = str(
        context
    ).casefold()

    assert "provider_id" not in text
    assert "capability_name" not in text

    assert (
        value.resources[0]
        .resource_handle
        in text
    )
