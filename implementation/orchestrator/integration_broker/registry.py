"""Integration Broker backed by Jason's authoritative kernel registries.

The broker does not create provider authority.

Registration succeeds only when:
- the referenced execution provider exists,
- every manifest operation references a registered governed capability,
- the referenced provider declares support for every such capability.

Current health/lifecycle/approval are read from the Execution Provider Registry
whenever the broker produces a runtime view.
"""

from __future__ import annotations

from typing import Dict, Tuple

from kernel.capabilities import CapabilityRegistryService
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)

from .contracts import (
    IntegrationManifest,
    IntegrationOperation,
    IntegrationRuntimeView,
)


class IntegrationBrokerError(RuntimeError):
    pass


class DuplicateIntegrationError(IntegrationBrokerError):
    pass


class IntegrationNotFoundError(IntegrationBrokerError):
    pass


class IntegrationManifestValidationError(IntegrationBrokerError):
    pass


class IntegrationBroker:
    def __init__(
        self,
        *,
        capabilities: CapabilityRegistryService,
        providers: ExecutionProviderRegistryService,
    ) -> None:
        self._capabilities = capabilities
        self._providers = providers
        self._integrations: Dict[str, IntegrationManifest] = {}

    def register(self, manifest: IntegrationManifest) -> None:
        if manifest.integration_id in self._integrations:
            raise DuplicateIntegrationError(manifest.integration_id)

        self._validate_manifest(manifest)
        self._integrations[manifest.integration_id] = manifest

    def get_manifest(self, integration_id: str) -> IntegrationManifest:
        try:
            return self._integrations[integration_id]
        except KeyError as exc:
            raise IntegrationNotFoundError(integration_id) from exc

    def get(self, integration_id: str) -> IntegrationRuntimeView:
        return self._runtime_view(self.get_manifest(integration_id))

    def list_integrations(self) -> Tuple[IntegrationRuntimeView, ...]:
        return tuple(
            self._runtime_view(self._integrations[key])
            for key in sorted(self._integrations)
        )

    def integrations_for_resource(
        self,
        resource_type: str,
        *,
        include_nonoperational: bool = False,
    ) -> Tuple[IntegrationRuntimeView, ...]:
        result = []

        for view in self.list_integrations():
            if (
                not include_nonoperational
                and not view.operational
            ):
                continue

            if view.resource(resource_type) is not None:
                result.append(view)

        return tuple(result)

    def operations_for_resource(
        self,
        resource_type: str,
        *,
        include_nonoperational: bool = False,
    ) -> Tuple[
        tuple[IntegrationRuntimeView, IntegrationOperation],
        ...
    ]:
        result = []

        for view in self.integrations_for_resource(
            resource_type,
            include_nonoperational=include_nonoperational,
        ):
            resource = view.resource(resource_type)
            assert resource is not None

            for operation in resource.operations:
                result.append((view, operation))

        return tuple(result)

    def _validate_manifest(
        self,
        manifest: IntegrationManifest,
    ) -> None:
        try:
            provider = self._providers.get(manifest.provider_id)
        except LookupError as exc:
            raise IntegrationManifestValidationError(
                "integration references an unregistered provider: "
                f"{manifest.provider_id}"
            ) from exc

        for resource in manifest.resources:
            selector_names = {
                selector.name
                for selector in resource.selectors
            }

            for operation in resource.operations:
                unknown_selectors = (
                    set(operation.selector_names)
                    - selector_names
                )
                if unknown_selectors:
                    raise IntegrationManifestValidationError(
                        "operation references selectors not declared by its "
                        f"resource: integration={manifest.integration_id}; "
                        f"resource={resource.resource_type}; "
                        f"operation={operation.operation_id}; "
                        f"selectors={tuple(sorted(unknown_selectors))}"
                    )

                try:
                    capability = self._capabilities.get_current(
                        capability_name=operation.capability_name,
                        allow_pilot=True,
                    )
                except LookupError as exc:
                    raise IntegrationManifestValidationError(
                        "integration operation references an unavailable "
                        "governed capability: "
                        f"{operation.capability_name}"
                    ) from exc

                if operation.capability_name not in provider.capabilities:
                    raise IntegrationManifestValidationError(
                        "provider does not declare support for manifest "
                        "capability: "
                        f"provider={manifest.provider_id}; "
                        f"capability={operation.capability_name}"
                    )

                declared_read_only = str(
                    capability.metadata.get("read_only", "")
                ).strip().casefold()

                if (
                    declared_read_only == "true"
                    and not operation.read_only
                ):
                    raise IntegrationManifestValidationError(
                        "manifest cannot describe a governed read-only "
                        "capability as mutable: "
                        f"{operation.capability_name}"
                    )

    def _runtime_view(
        self,
        manifest: IntegrationManifest,
    ) -> IntegrationRuntimeView:
        provider = self._providers.get(manifest.provider_id)

        operational = (
            provider.lifecycle_status
            is ProviderLifecycle.AVAILABLE
            and provider.approval_status
            in {
                ProviderApproval.APPROVED,
                ProviderApproval.PILOT,
            }
            and provider.health_status
            in {
                ProviderHealth.HEALTHY,
                ProviderHealth.WARNING,
            }
        )

        return IntegrationRuntimeView(
            manifest=manifest,
            provider_health=provider.health_status.value,
            provider_lifecycle=provider.lifecycle_status.value,
            provider_approval=provider.approval_status.value,
            operational=operational,
        )
