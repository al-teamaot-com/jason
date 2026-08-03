from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class OperationDefinition:
    method: str
    path_template: str
    path_arguments: tuple[str, ...] = ()
    parameter_mappings: Mapping[str, str] | None = None
    optional_parameters: frozenset[str] = frozenset()


IT_GLUE_OPERATIONS: Mapping[str, OperationDefinition] = {
    "it_glue.organization.get": OperationDefinition(
        method="GET",
        path_template="/organizations/{organization_id}",
        path_arguments=("organization_id",),
    ),
    "it_glue.configuration.search": OperationDefinition(
        method="GET",
        path_template="/configurations",
        parameter_mappings={
            "organization_id": "filter[organization_id]",
            "name": "filter[name]",
        },
        optional_parameters=frozenset({"name"}),
    ),
    "it_glue.flexible_asset.search": OperationDefinition(
        method="GET",
        path_template="/flexible_assets",
        parameter_mappings={
            "organization_id": "filter[organization_id]",
            "flexible_asset_type_id": (
                "filter[flexible_asset_type_id]"
            ),
        },
        optional_parameters=frozenset(
            {"flexible_asset_type_id"}
        ),
    ),
    "it_glue.document.get": OperationDefinition(
        method="GET",
        path_template="/documents/{document_id}",
        path_arguments=("document_id",),
    ),
    "it_glue.relationships.list": OperationDefinition(
        method="GET",
        path_template="/relationships",
        parameter_mappings={
            "resource_type": "filter[resource_type]",
            "resource_id": "filter[resource_id]",
        },
    ),
}


def resolve_operation(
    capability: str,
    arguments: Mapping[str, Any],
) -> tuple[str, str, Mapping[str, Any] | None]:
    definition = IT_GLUE_OPERATIONS.get(capability)

    if definition is None:
        raise ValueError(
            f"Unsupported capability: {capability}"
        )

    path_values: dict[str, int] = {}

    for argument_name in definition.path_arguments:
        if argument_name not in arguments:
            raise ValueError(
                f"Required argument is missing: {argument_name}"
            )

        try:
            path_values[argument_name] = int(
                arguments[argument_name]
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Argument must be an integer: {argument_name}"
            ) from error

    path = definition.path_template.format(
        **path_values
    )

    params: dict[str, Any] = {}

    for argument_name, provider_name in (
        definition.parameter_mappings or {}
    ).items():
        if argument_name not in arguments:
            if argument_name in definition.optional_parameters:
                continue

            raise ValueError(
                f"Required argument is missing: {argument_name}"
            )

        value = arguments[argument_name]

        if value is None:
            if argument_name in definition.optional_parameters:
                continue

            raise ValueError(
                f"Required argument is missing: {argument_name}"
            )

        params[provider_name] = value

    return (
        definition.method,
        path,
        params or None,
    )
