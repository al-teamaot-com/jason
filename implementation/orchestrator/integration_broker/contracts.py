"""Provider-neutral Integration Broker contracts.

The integration manifest is descriptive:
- what resources the integration can observe,
- what governed operations it can satisfy,
- how those resources may be selected and related.

Runtime health, lifecycle, approval, and capability authority are NOT copied
into the manifest. Those remain authoritative in Jason's kernel registries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Tuple


class OperationKind(str, Enum):
    SEARCH = "search"
    READ = "read"
    LIST = "list"
    CREATE = "create"
    UPDATE = "update"
    EXECUTE = "execute"


@dataclass(frozen=True)
class SelectorDefinition:
    name: str
    description: str
    verified_identity_required: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("selector name must be non-empty")
        if not self.description.strip():
            raise ValueError("selector description must be non-empty")


@dataclass(frozen=True)
class IntegrationOperation:
    operation_id: str
    kind: OperationKind
    capability_name: str
    description: str
    read_only: bool
    selector_names: Tuple[str, ...] = ()
    collection_supported: bool = False

    def __post_init__(self) -> None:
        if not self.operation_id.strip():
            raise ValueError("operation_id must be non-empty")
        if not self.capability_name.strip():
            raise ValueError("capability_name must be non-empty")
        if not self.description.strip():
            raise ValueError("operation description must be non-empty")


@dataclass(frozen=True)
class ResourceObservation:
    """Semantic description of evidence this integration may contribute."""

    name: str
    description: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("observation name must be non-empty")
        if not self.description.strip():
            raise ValueError("observation description must be non-empty")


@dataclass(frozen=True)
class ResourceDefinition:
    resource_type: str
    description: str
    operations: Tuple[IntegrationOperation, ...]
    selectors: Tuple[SelectorDefinition, ...] = ()
    observations: Tuple[ResourceObservation, ...] = ()
    relationships: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.resource_type.strip():
            raise ValueError("resource_type must be non-empty")
        if not self.description.strip():
            raise ValueError("resource description must be non-empty")

        operation_ids = [item.operation_id for item in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError(
                f"duplicate operation_id for resource {self.resource_type}"
            )


@dataclass(frozen=True)
class IntegrationManifest:
    integration_id: str
    display_name: str
    manifest_version: str
    provider_id: str
    resources: Tuple[ResourceDefinition, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.integration_id.strip():
            raise ValueError("integration_id must be non-empty")
        if not self.display_name.strip():
            raise ValueError("display_name must be non-empty")
        if not self.manifest_version.strip():
            raise ValueError("manifest_version must be non-empty")
        if not self.provider_id.strip():
            raise ValueError("provider_id must be non-empty")

        resource_types = [item.resource_type for item in self.resources]
        if len(resource_types) != len(set(resource_types)):
            raise ValueError(
                f"duplicate resource_type in integration {self.integration_id}"
            )

    def resource(self, resource_type: str) -> ResourceDefinition | None:
        for resource in self.resources:
            if resource.resource_type == resource_type:
                return resource
        return None


@dataclass(frozen=True)
class IntegrationRuntimeView:
    """Current broker view composed from manifest + authoritative kernel state."""

    manifest: IntegrationManifest
    provider_health: str
    provider_lifecycle: str
    provider_approval: str
    operational: bool

    @property
    def integration_id(self) -> str:
        return self.manifest.integration_id

    @property
    def provider_id(self) -> str:
        return self.manifest.provider_id

    @property
    def display_name(self) -> str:
        return self.manifest.display_name

    @property
    def resources(self) -> Tuple[ResourceDefinition, ...]:
        return self.manifest.resources

    def resource(self, resource_type: str) -> ResourceDefinition | None:
        return self.manifest.resource(resource_type)
