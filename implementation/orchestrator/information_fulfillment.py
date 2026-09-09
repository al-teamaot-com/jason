"""Structural, provider-neutral fulfillment planning for Conversation Kernel needs.

The conversation layer describes what the human needs. This module determines the
smallest initial governed resource access required to begin satisfying that need.
It never uses question phrases, semantic hint lists, provider identities, connector
names, or question-specific mappings.
"""

from __future__ import annotations

from dataclasses import dataclass

from kernel.capabilities import (
    CapabilityDefinition,
    CapabilityLifecycle,
    CapabilityRegistryService,
)

from .conversation_kernel import InformationNeed


@dataclass(frozen=True, slots=True)
class FulfillmentCapability:
    capability_name: str
    resource_types: tuple[str, ...]
    operation: str
    selector_keys: tuple[str, ...]
    role: str
    permission_mode: str
    risk: str
    description: str

    def __post_init__(self) -> None:
        if not self.capability_name.strip() or not self.operation.strip():
            raise ValueError("fulfillment capability name and operation are required")
        if not self.resource_types:
            raise ValueError("fulfillment capability requires resource types")
        if self.role not in {"primary", "specialized"}:
            raise ValueError("fulfillment capability role is invalid")


@dataclass(frozen=True, slots=True)
class RegistryBackedFulfillmentCatalog:
    """Expose only structural governed capability facts needed for fulfillment."""

    registry: CapabilityRegistryService
    include_pilot: bool = True

    def list_available(self) -> tuple[FulfillmentCapability, ...]:
        items: list[FulfillmentCapability] = []
        for capability in self.registry.list_all():
            if capability.lifecycle_status is CapabilityLifecycle.ACTIVE:
                pass
            elif self.include_pilot and capability.lifecycle_status is CapabilityLifecycle.PILOT:
                pass
            else:
                continue
            converted = _convert(capability)
            if converted is not None:
                items.append(converted)
        return tuple(sorted(items, key=lambda item: item.capability_name))

    def for_resource(self, resource_type: str) -> tuple[FulfillmentCapability, ...]:
        kind = resource_type.strip()
        if not kind:
            raise ValueError("resource type is required")
        return tuple(
            item for item in self.list_available() if kind in item.resource_types
        )


@dataclass(frozen=True, slots=True)
class FulfillmentStep:
    """A structural capability choice; argument grounding and execution remain separate."""

    capability_name: str
    target_reference: str
    target_source: str
    information_need: str
    authority: str


@dataclass(frozen=True, slots=True)
class InitialFulfillmentPlan:
    """The minimum initial evidence acquisition for one information need."""

    steps: tuple[FulfillmentStep, ...]
    expansion_allowed: bool = True

    def __post_init__(self) -> None:
        if len(self.steps) != 1:
            raise ValueError("initial fulfillment plan must contain exactly one primary step")


@dataclass(frozen=True, slots=True)
class GovernedInitialFulfillmentPlanner:
    """Start with one primary resource access; expand only after evidence is insufficient.

    This planner deliberately does not ask a language model to guess every possible
    evidence source up front. For an information read, Jason begins with the registered
    primary resource capability matching the target and reference form. Specialized
    resources are considered only by a later evidence-gap step when the primary result
    cannot satisfy the information need.
    """

    catalog: RegistryBackedFulfillmentCatalog

    def plan(self, need: InformationNeed) -> InitialFulfillmentPlan:
        if need.authority != "observe":
            raise PermissionError(
                "non-observe information needs require the governed action fulfillment path"
            )

        candidates = tuple(
            item
            for item in self.catalog.for_resource(need.target.kind)
            if item.permission_mode == "observe"
            and item.role == "primary"
            and item.operation in {"search", "read"}
        )
        if not candidates:
            raise LookupError(
                "no primary governed read capability is registered for the information target"
            )

        operation_order = (
            ("read", "search")
            if need.target.source == "verified_entity"
            else ("search", "read")
        )
        selected: FulfillmentCapability | None = None
        for operation in operation_order:
            matching = tuple(item for item in candidates if item.operation == operation)
            if len(matching) == 1:
                selected = matching[0]
                break
            if len(matching) > 1:
                raise LookupError(
                    "multiple primary governed capabilities claim the same structural resource operation"
                )
        if selected is None:
            raise LookupError(
                "no primary governed capability supports the target reference form"
            )

        return InitialFulfillmentPlan(
            steps=(
                FulfillmentStep(
                    capability_name=selected.capability_name,
                    target_reference=need.target.reference,
                    target_source=need.target.source,
                    information_need=need.need,
                    authority=need.authority,
                ),
            )
        )


def _convert(capability: CapabilityDefinition) -> FulfillmentCapability | None:
    metadata = capability.metadata
    if str(metadata.get("provider_neutral", "")).strip().casefold() != "true":
        return None

    resource_types = _csv(metadata.get("resource_types", ""))
    operation = str(metadata.get("operation", "")).strip().casefold()
    if not resource_types or not operation:
        return None

    read_only = str(metadata.get("read_only", "")).strip().casefold() == "true"
    permission_mode = str(
        metadata.get(
            "conversation_permission_mode",
            "observe" if read_only else "execute",
        )
    ).strip()
    role = str(metadata.get("resource_role", "")).strip().casefold()
    if not role:
        # Backward-compatible structural inference while existing registrations are
        # migrated: a capability that declares exactly one resource type is a base
        # resource operation; compound resource types are specialized projections.
        role = "primary" if len(resource_types) == 1 else "specialized"

    return FulfillmentCapability(
        capability_name=capability.capability_name,
        resource_types=resource_types,
        operation=operation,
        selector_keys=_csv(metadata.get("selector_keys", "")),
        role=role,
        permission_mode=permission_mode,
        risk=capability.risk_level.value,
        description=" ".join(
            part
            for part in (
                capability.display_name.strip(),
                capability.business_purpose.strip(),
            )
            if part
        ),
    )


def _csv(value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            item.strip()
            for item in str(value).split(",")
            if item.strip()
        )
    )
