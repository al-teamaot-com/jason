from __future__ import annotations

from kernel.capabilities.contracts import (
    CapabilityDefinition,
    CapabilityLifecycle,
    CapabilityQuery,
)
from kernel.capabilities.repository import (
    InMemoryCapabilityRegistry,
)


class CapabilityRegistryService:
    def __init__(
        self,
        *,
        registry: InMemoryCapabilityRegistry,
    ) -> None:
        self._registry = registry

    def register(
        self,
        capability: CapabilityDefinition,
    ) -> None:
        self._validate_governance(capability)
        self._registry.register(capability)

    def get(
        self,
        *,
        capability_name: str,
        version: str,
    ) -> CapabilityDefinition:
        return self._registry.get(
            capability_name=capability_name,
            version=version,
        )

    def list_all(self) -> tuple[CapabilityDefinition, ...]:
        return self._registry.list_all()

    def find(
        self,
        query: CapabilityQuery,
    ) -> tuple[CapabilityDefinition, ...]:
        return self._registry.find(query)

    def get_current(
        self,
        *,
        capability_name: str,
        allow_pilot: bool = False,
    ) -> CapabilityDefinition:
        return self._registry.get_current(
            capability_name=capability_name,
            allow_pilot=allow_pilot,
        )

    def set_lifecycle(
        self,
        *,
        capability_name: str,
        version: str,
        lifecycle_status: CapabilityLifecycle,
    ) -> CapabilityDefinition:
        current = self._registry.get(
            capability_name=capability_name,
            version=version,
        )

        candidate = CapabilityDefinition(
            capability_name=current.capability_name,
            version=current.version,
            display_name=current.display_name,
            lifecycle_status=lifecycle_status,
            business_purpose=current.business_purpose,
            owner_service=current.owner_service,
            architectural_capability_ids=(
                current.architectural_capability_ids
            ),
            risk_level=current.risk_level,
            data_classifications=current.data_classifications,
            permitted_execution_modes=(
                current.permitted_execution_modes
            ),
            input_schema_reference=(
                current.input_schema_reference
            ),
            output_schema_reference=(
                current.output_schema_reference
            ),
            invoking_roles=current.invoking_roles,
            approval=current.approval,
            evidence=current.evidence,
            dependencies=current.dependencies,
            idempotency_behavior=(
                current.idempotency_behavior
            ),
            idempotency_key_required=(
                current.idempotency_key_required
            ),
            timeout_seconds=current.timeout_seconds,
            maximum_attempts=current.maximum_attempts,
            failure_behavior=current.failure_behavior,
            tenant_isolation_required=(
                current.tenant_isolation_required
            ),
            client_isolation_required=(
                current.client_isolation_required
            ),
            stewardship=current.stewardship,
            created_at=current.created_at,
            metadata=current.metadata,
        )

        self._validate_governance(candidate)

        return self._registry.update_lifecycle(
            capability_name=capability_name,
            version=version,
            lifecycle_status=lifecycle_status,
        )

    @staticmethod
    def _validate_governance(
        capability: CapabilityDefinition,
    ) -> None:
        if capability.lifecycle_status not in {
            CapabilityLifecycle.PILOT,
            CapabilityLifecycle.ACTIVE,
        }:
            return

        if not capability.business_purpose.strip():
            raise ValueError(
                "Pilot and active capabilities require "
                "a business purpose."
            )

        if not capability.owner_service.strip():
            raise ValueError(
                "Pilot and active capabilities require "
                "an owner service."
            )

        if not capability.architectural_capability_ids:
            raise ValueError(
                "Pilot and active capabilities require "
                "an architectural capability ID."
            )

        if not capability.data_classifications:
            raise ValueError(
                "Pilot and active capabilities require "
                "a data classification."
            )

        if not capability.permitted_execution_modes:
            raise ValueError(
                "Pilot and active capabilities require "
                "an execution mode."
            )

        if not capability.input_schema_reference.strip():
            raise ValueError(
                "Pilot and active capabilities require "
                "an input schema reference."
            )

        if not capability.output_schema_reference.strip():
            raise ValueError(
                "Pilot and active capabilities require "
                "an output schema reference."
            )

        if not capability.invoking_roles:
            raise ValueError(
                "Pilot and active capabilities require "
                "an invoking role."
            )

        if not capability.failure_behavior.strip():
            raise ValueError(
                "Pilot and active capabilities require "
                "explicit failure behavior."
            )
