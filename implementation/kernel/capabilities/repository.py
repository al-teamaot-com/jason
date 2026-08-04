from __future__ import annotations

from dataclasses import replace

from kernel.capabilities.contracts import (
    CapabilityDefinition,
    CapabilityLifecycle,
    CapabilityQuery,
)


class DuplicateCapabilityError(ValueError):
    """Raised when a capability name and version already exist."""


class CapabilityNotFoundError(LookupError):
    """Raised when a capability definition does not exist."""


class InMemoryCapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[
            tuple[str, str],
            CapabilityDefinition,
        ] = {}

    def register(
        self,
        capability: CapabilityDefinition,
    ) -> None:
        key = (
            capability.capability_name,
            capability.version,
        )

        if key in self._capabilities:
            raise DuplicateCapabilityError(
                "Capability already exists: "
                f"{capability.capability_name}@{capability.version}"
            )

        self._capabilities[key] = capability

    def get(
        self,
        *,
        capability_name: str,
        version: str,
    ) -> CapabilityDefinition:
        key = (capability_name, version)

        try:
            return self._capabilities[key]
        except KeyError as error:
            raise CapabilityNotFoundError(
                "Capability was not found: "
                f"{capability_name}@{version}"
            ) from error

    def list_all(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(
            sorted(
                self._capabilities.values(),
                key=lambda capability: (
                    capability.capability_name,
                    self._version_key(capability.version),
                ),
            )
        )

    def find(
        self,
        query: CapabilityQuery,
    ) -> tuple[CapabilityDefinition, ...]:
        matches: list[CapabilityDefinition] = []

        for capability in self._capabilities.values():
            if (
                query.lifecycle_status is not None
                and capability.lifecycle_status
                is not query.lifecycle_status
            ):
                continue

            if (
                query.architectural_capability_id is not None
                and query.architectural_capability_id
                not in capability.architectural_capability_ids
            ):
                continue

            if (
                query.execution_mode is not None
                and query.execution_mode
                not in capability.permitted_execution_modes
            ):
                continue

            if (
                query.risk_level is not None
                and capability.risk_level
                is not query.risk_level
            ):
                continue

            matches.append(capability)

        return tuple(
            sorted(
                matches,
                key=lambda capability: (
                    capability.capability_name,
                    self._version_key(capability.version),
                ),
            )
        )

    def get_current(
        self,
        *,
        capability_name: str,
        allow_pilot: bool = False,
    ) -> CapabilityDefinition:
        eligible_lifecycles = {
            CapabilityLifecycle.ACTIVE,
        }

        if allow_pilot:
            eligible_lifecycles.add(
                CapabilityLifecycle.PILOT
            )

        matches = [
            capability
            for capability in self._capabilities.values()
            if (
                capability.capability_name == capability_name
                and capability.lifecycle_status
                in eligible_lifecycles
            )
        ]

        if not matches:
            raise CapabilityNotFoundError(
                "No current capability version was found: "
                f"{capability_name}"
            )

        return max(
            matches,
            key=lambda capability: self._version_key(
                capability.version
            ),
        )

    def update_lifecycle(
        self,
        *,
        capability_name: str,
        version: str,
        lifecycle_status: CapabilityLifecycle,
    ) -> CapabilityDefinition:
        current = self.get(
            capability_name=capability_name,
            version=version,
        )

        updated = replace(
            current,
            lifecycle_status=lifecycle_status,
        )

        self._capabilities[
            (capability_name, version)
        ] = updated

        return updated

    @staticmethod
    def _version_key(version: str) -> tuple[int, ...]:
        return tuple(
            int(part)
            for part in version.split(".")
        )
