from __future__ import annotations

import pytest

from connectors.it_glue.operations import (
    IT_GLUE_OPERATIONS,
    resolve_operation,
)


@pytest.mark.parametrize(
    (
        "capability",
        "arguments",
        "expected_path",
        "expected_params",
    ),
    [
        (
            "it_glue.organization.get",
            {"organization_id": "42"},
            "/organizations/42",
            None,
        ),
        (
            "it_glue.configuration.search",
            {
                "organization_id": 42,
                "name": "Firewall",
            },
            "/configurations",
            {
                "filter[organization_id]": 42,
                "filter[name]": "Firewall",
            },
        ),
        (
            "it_glue.configuration.search",
            {"organization_id": 42},
            "/configurations",
            {
                "filter[organization_id]": 42,
            },
        ),
        (
            "it_glue.flexible_asset.search",
            {
                "organization_id": 42,
                "flexible_asset_type_id": 9,
            },
            "/flexible_assets",
            {
                "filter[organization_id]": 42,
                "filter[flexible_asset_type_id]": 9,
            },
        ),
        (
            "it_glue.document.get",
            {"document_id": 73},
            "/documents/73",
            None,
        ),
        (
            "it_glue.relationships.list",
            {
                "resource_type": "Configuration",
                "resource_id": 88,
            },
            "/relationships",
            {
                "filter[resource_type]": "Configuration",
                "filter[resource_id]": 88,
            },
        ),
    ],
)
def test_resolves_registered_operation(
    capability,
    arguments,
    expected_path,
    expected_params,
) -> None:
    method, path, params = resolve_operation(
        capability,
        arguments,
    )

    assert method == "GET"
    assert path == expected_path
    assert params == expected_params


def test_registry_matches_connector_capabilities() -> None:
    assert set(IT_GLUE_OPERATIONS) == {
        "it_glue.organization.get",
        "it_glue.configuration.search",
        "it_glue.flexible_asset.search",
        "it_glue.document.get",
        "it_glue.relationships.list",
    }


def test_rejects_unknown_operation() -> None:
    with pytest.raises(
        ValueError,
        match="Unsupported capability",
    ):
        resolve_operation(
            "it_glue.password.delete",
            {},
        )


def test_rejects_missing_path_argument() -> None:
    with pytest.raises(
        ValueError,
        match="organization_id",
    ):
        resolve_operation(
            "it_glue.organization.get",
            {},
        )


def test_rejects_invalid_path_argument() -> None:
    with pytest.raises(
        ValueError,
        match="must be an integer",
    ):
        resolve_operation(
            "it_glue.document.get",
            {"document_id": "not-a-number"},
        )


def test_rejects_missing_required_query_argument() -> None:
    with pytest.raises(
        ValueError,
        match="organization_id",
    ):
        resolve_operation(
            "it_glue.configuration.search",
            {},
        )


def test_rejects_missing_relationship_resource_type() -> None:
    with pytest.raises(
        ValueError,
        match="resource_type",
    ):
        resolve_operation(
            "it_glue.relationships.list",
            {"resource_id": 88},
        )
