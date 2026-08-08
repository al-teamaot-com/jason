from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol


class ResourceOperation(str, Enum):
    DESCRIBE = "describe"
    GET = "get"
    QUERY = "query"
    RELATIONSHIPS = "relationships"
    ACTIONS = "actions"


@dataclass(frozen=True)
class ResourceTypeDefinition:
    name: str
    provider: str
    provider_type: str
    operations: frozenset[ResourceOperation]
    client_scoped: bool = True
    mutable: bool = False

    def __post_init__(self) -> None:
        for field_name, value in (
            ("name", self.name),
            ("provider", self.provider),
            ("provider_type", self.provider_type),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not self.operations:
            raise ValueError("operations must not be empty")


@dataclass(frozen=True)
class ResourceQuery:
    provider: str
    resource_type: str
    operation: ResourceOperation
    organization_id: str | None = None
    resource_id: str | None = None
    filters: Mapping[str, Any] | None = None
    page_size: int | None = None
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider must be non-empty")
        if not self.resource_type.strip():
            raise ValueError("resource_type must be non-empty")
        if self.page_size is not None and not 1 <= self.page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")


class ResourceProvider(Protocol):
    def execute_resource_query(self, query: ResourceQuery) -> Mapping[str, Any]:
        ...


class ResourceRegistry:
    """Canonical allow-list for provider resource families.

    The registry describes what Jason may ask a provider for. It does not
    contain credentials, provider endpoints, or network behavior.
    """

    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], ResourceTypeDefinition] = {}

    def register(self, definition: ResourceTypeDefinition) -> None:
        key = (definition.provider, definition.name)
        if key in self._definitions:
            raise ValueError(
                f"Resource type is already registered: {definition.provider}.{definition.name}"
            )
        self._definitions[key] = definition

    def resolve(self, provider: str, resource_type: str) -> ResourceTypeDefinition:
        try:
            return self._definitions[(provider, resource_type)]
        except KeyError as error:
            raise ValueError(
                f"Resource type is not registered: {provider}.{resource_type}"
            ) from error

    def authorize(self, query: ResourceQuery) -> ResourceTypeDefinition:
        definition = self.resolve(query.provider, query.resource_type)

        if query.operation not in definition.operations:
            raise ValueError(
                f"Operation {query.operation.value!r} is not approved for "
                f"{query.provider}.{query.resource_type}"
            )

        if definition.client_scoped and not query.organization_id:
            raise ValueError(
                f"organization_id is required for {query.provider}.{query.resource_type}"
            )

        if query.operation is ResourceOperation.GET and not query.resource_id:
            raise ValueError("resource_id is required for get operations")

        return definition

    def list_provider_resources(self, provider: str) -> tuple[ResourceTypeDefinition, ...]:
        return tuple(
            definition
            for (registered_provider, _), definition in sorted(self._definitions.items())
            if registered_provider == provider
        )


READ_ONLY_OPERATIONS = frozenset(
    {
        ResourceOperation.DESCRIBE,
        ResourceOperation.GET,
        ResourceOperation.QUERY,
        ResourceOperation.RELATIONSHIPS,
        ResourceOperation.ACTIONS,
    }
)
