"""Provider-neutral reasoning projection for the Integration Broker.

The model receives opaque compiled operation references. Each reference binds one
currently operational integration + resource + operation. The model therefore
cannot independently combine a valid resource from one integration with an
operation from another.

Provider IDs, capability names, connector names, and API details remain runtime
implementation details.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from .contracts import (
    IntegrationOperation,
    IntegrationRuntimeView,
    ResourceDefinition,
)
from .registry import IntegrationBroker


@dataclass(frozen=True, slots=True)
class BrokerOperationTarget:
    operation_ref: str
    integration: IntegrationRuntimeView
    resource: ResourceDefinition
    operation: IntegrationOperation


def _resource_ref(
    *,
    integration_id: str,
    resource_type: str,
) -> str:
    digest = sha256(
        f"{integration_id}|{resource_type}".encode("utf-8")
    ).hexdigest()[:20]

    return f"resource_{digest}"


def _operation_ref(
    *,
    integration_id: str,
    resource_type: str,
    operation_id: str,
) -> str:
    digest = sha256(
        (
            f"{integration_id}|"
            f"{resource_type}|"
            f"{operation_id}"
        ).encode("utf-8")
    ).hexdigest()[:24]

    return f"operation_{digest}"


def broker_operation_targets(
    broker: IntegrationBroker,
) -> tuple[BrokerOperationTarget, ...]:
    targets: list[BrokerOperationTarget] = []

    for view in broker.list_integrations():
        if not view.operational:
            continue

        for resource in view.resources:
            for operation in resource.operations:
                targets.append(
                    BrokerOperationTarget(
                        operation_ref=_operation_ref(
                            integration_id=view.integration_id,
                            resource_type=resource.resource_type,
                            operation_id=operation.operation_id,
                        ),
                        integration=view,
                        resource=resource,
                        operation=operation,
                    )
                )

    return tuple(
        sorted(
            targets,
            key=lambda item: item.operation_ref,
        )
    )


def resolve_operation_ref(
    broker: IntegrationBroker,
    operation_ref: str,
) -> BrokerOperationTarget:
    for target in broker_operation_targets(broker):
        if target.operation_ref == operation_ref:
            return target

    raise LookupError(
        f"broker operation reference is not currently available: "
        f"{operation_ref}"
    )


def broker_model_context(
    broker: IntegrationBroker,
) -> Mapping[str, Any]:
    resources: list[dict[str, Any]] = []

    for view in broker.list_integrations():
        if not view.operational:
            continue

        for resource in view.resources:
            resource_ref = _resource_ref(
                integration_id=view.integration_id,
                resource_type=resource.resource_type,
            )

            resources.append(
                {
                    "resource_ref": resource_ref,
                    "resource_type": resource.resource_type,
                    "description": resource.description,
                    "selectors": [
                        {
                            "name": selector.name,
                            "description": selector.description,
                            "verified_identity_required": (
                                selector.verified_identity_required
                            ),
                        }
                        for selector in resource.selectors
                    ],
                    "observations": [
                        {
                            "name": observation.name,
                            "description": observation.description,
                        }
                        for observation in resource.observations
                    ],
                    "relationships": list(
                        resource.relationships
                    ),
                    "operations": [
                        {
                            "operation_ref": _operation_ref(
                                integration_id=view.integration_id,
                                resource_type=resource.resource_type,
                                operation_id=operation.operation_id,
                            ),
                            "kind": operation.kind.value,
                            "description": operation.description,
                            "read_only": operation.read_only,
                            "selector_names": list(
                                operation.selector_names
                            ),
                            "collection_supported": (
                                operation.collection_supported
                            ),
                        }
                        for operation in resource.operations
                    ],
                }
            )

    return {
        "resources": resources,
    }
