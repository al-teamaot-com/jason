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


APPROVED_IT_GLUE_ENTITIES: Mapping[str, str] = {
    "Organizations": "organizations",
    "Configurations": "configurations",
    "FlexibleAssets": "flexible_assets",
    "Documents": "documents",
    "Contacts": "contacts",
    "Locations": "locations",
}


IT_GLUE_OPERATIONS: Mapping[str, OperationDefinition] = {
    "it_glue.entity.get": OperationDefinition(
        method="GET",
        path_template="/{entity_path}/{entity_id}",
        path_arguments=("entity_path", "entity_id"),
    ),
    "it_glue.entity.query": OperationDefinition(
        method="GET",
        path_template="/{entity_path}",
        path_arguments=("entity_path",),
    ),
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

    path_values: dict[str, str | int] = {}

    for argument_name in definition.path_arguments:
        if argument_name == "entity_path":
            entity = arguments.get("entity")

            if not isinstance(entity, str):
                raise ValueError(
                    "Required argument is missing: entity"
                )

            entity_path = APPROVED_IT_GLUE_ENTITIES.get(
                entity
            )

            if entity_path is None:
                raise ValueError(
                    f"IT Glue entity is not approved: {entity!r}"
                )

            path_values[argument_name] = entity_path
            continue

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

    if capability == "it_glue.entity.query":
        filters = arguments.get("filters", {})

        if not isinstance(filters, Mapping):
            raise ValueError(
                "IT Glue query filters must be a mapping."
            )

        for field_name, value in filters.items():
            if (
                not isinstance(field_name, str)
                or not field_name.strip()
            ):
                raise ValueError(
                    "IT Glue query filter names must be "
                    "non-empty strings."
                )

            params[f"filter[{field_name}]"] = value

        page_number = arguments.get("page_number")
        if page_number is not None:
            try:
                page_number = int(page_number)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "page_number must be an integer."
                ) from error

            if page_number < 1:
                raise ValueError(
                    "page_number must be at least 1."
                )

            params["page[number]"] = page_number

        page_size = arguments.get("page_size")
        if page_size is not None:
            try:
                page_size = int(page_size)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "page_size must be an integer."
                ) from error

            if not 1 <= page_size <= 1000:
                raise ValueError(
                    "page_size must be between 1 and 1000."
                )

            params["page[size]"] = page_size

    return (
        definition.method,
        path,
        params or None,
    )
