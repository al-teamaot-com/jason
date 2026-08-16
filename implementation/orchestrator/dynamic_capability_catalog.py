"""Adapt Jason's governed Capability Registry into a bounded conversation catalog.

This adapter intentionally does not consume legacy semantic hint metadata such as
fact_hints, canonical_facts, inquiry_hints, or phrase mappings.  The conversational
planner sees capabilities that actually exist at runtime, their governed business
purpose, lifecycle/risk/permission posture, schema references, and structural input
metadata declared by the capability itself. Provider selection remains the Central
Orchestrator's responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from kernel.capabilities import (
    CapabilityDefinition,
    CapabilityLifecycle,
    CapabilityRegistryService,
)

from .dynamic_conversation_kernel import OfferedConversationCapability


_ALLOWED_PERMISSION_MODES = {
    "observe",
    "recommend",
    "request_approval",
    "execute",
    "administer",
}


@dataclass(frozen=True, slots=True)
class RegistryBackedDynamicCapabilityCatalog:
    """Produce the current model-visible capability set from governed registry truth."""

    registry: CapabilityRegistryService
    include_pilot: bool = True

    def list_offered(self) -> tuple[OfferedConversationCapability, ...]:
        offered: list[OfferedConversationCapability] = []
        for capability in self.registry.list_all():
            if capability.lifecycle_status is CapabilityLifecycle.ACTIVE:
                pass
            elif self.include_pilot and capability.lifecycle_status is CapabilityLifecycle.PILOT:
                pass
            else:
                continue
            offered.append(_offer(capability))
        return tuple(sorted(offered, key=lambda item: item.capability_id))


def _offer(capability: CapabilityDefinition) -> OfferedConversationCapability:
    metadata = capability.metadata
    permission_mode = _permission_mode(capability)
    structural = _structural_contract(metadata)

    description_parts = [
        capability.display_name.strip(),
        capability.business_purpose.strip(),
    ]
    resource_types = structural.get("resource_types", ())
    if resource_types:
        description_parts.append("Resource types: " + ", ".join(resource_types) + ".")
    operation = structural.get("operation")
    if operation:
        description_parts.append(f"Operation: {operation}.")
    selector_keys = structural.get("selector_keys", ())
    if selector_keys:
        description_parts.append("Accepted selector keys: " + ", ".join(selector_keys) + ".")

    return OfferedConversationCapability(
        capability_id=capability.capability_name,
        description=" ".join(part for part in description_parts if part),
        # Provider selection is deliberately absent here. A canonical capability can
        # gain or lose execution providers without changing conversation semantics.
        provider=None,
        input_schema={
            "$ref": capability.input_schema_reference,
            **({"selector_keys": list(selector_keys)} if selector_keys else {}),
        },
        output_schema={"$ref": capability.output_schema_reference},
        permission_mode=permission_mode,
        risk=capability.risk_level.value,
    )


def _permission_mode(capability: CapabilityDefinition) -> str:
    declared = str(capability.metadata.get("conversation_permission_mode", "")).strip()
    if declared:
        if declared not in _ALLOWED_PERMISSION_MODES:
            raise ValueError(
                f"capability {capability.capability_name} declares an invalid conversation permission mode"
            )
        return declared
    if str(capability.metadata.get("read_only", "")).strip().casefold() == "true":
        return "observe"
    # Generic fallback for non-read capabilities. This is authority intent, not a
    # permission grant; JKD-001 still decides whether the human may execute it.
    return "execute"


def _structural_contract(metadata: Mapping[str, str]) -> Mapping[str, object]:
    """Return only structural capability metadata, never legacy semantic hint lists."""

    resource_types = _csv(metadata.get("resource_types", ""))
    selector_keys = _csv(metadata.get("selector_keys", ""))
    operation = str(metadata.get("operation", "")).strip()
    result: dict[str, object] = {}
    if resource_types:
        result["resource_types"] = resource_types
    if selector_keys:
        result["selector_keys"] = selector_keys
    if operation:
        result["operation"] = operation
    return result


def _csv(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in str(value).split(",") if item.strip()))
