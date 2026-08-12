from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from kernel.capabilities import CapabilityDefinition, CapabilityRegistryService


@dataclass(frozen=True, slots=True)
class ResourceInquiry:
    """Provider-neutral description of information a human is asking Jason to obtain."""

    resource_type: str
    resource_selector: Mapping[str, Any]
    requested_facts: tuple[str, ...]
    execution_mode: str = "deterministic"
    permission_mode: str = "observe"
    result_intent: str = "summary"
    completeness_requirement: str = "sufficient"
    evidence_contexts: Mapping[str, tuple[str, ...]] | None = None
    relationship_type: str | None = None
    temporal_semantics: str = "unspecified"


    def __post_init__(self) -> None:
        if not self.resource_type.strip():
            raise ValueError("resource_type is required")
        if not self.requested_facts:
            raise ValueError("at least one requested fact is required")
        if not all(fact.strip() for fact in self.requested_facts):
            raise ValueError("requested facts must be non-empty")
        if not self.execution_mode.strip():
            raise ValueError("execution_mode is required")
        if self.permission_mode != "observe":
            raise PermissionError("resource inquiry planning is read-only")

        if self.result_intent not in {
            "summary",
            "enumerate",
            "count",
            "search",
            "inspect",
        }:
            raise ValueError("resource result_intent is invalid")
        if self.completeness_requirement not in {
            "sufficient",
            "complete",
        }:
            raise ValueError("resource completeness_requirement is invalid")
        if self.evidence_contexts is not None:
            unknown = set(self.evidence_contexts).difference(self.requested_facts)
            if unknown:
                raise ValueError(
                    "resource evidence contexts reference unrequested facts: "
                    + ", ".join(sorted(unknown))
                )
            for contexts in self.evidence_contexts.values():
                if any(not str(item).strip() for item in contexts):
                    raise ValueError("resource evidence contexts must be non-empty")
        if self.relationship_type is not None and not self.relationship_type.strip():
            raise ValueError("resource relationship_type must be non-empty when supplied")
        if self.temporal_semantics not in {
            "unspecified",
            "current",
            "most_recent",
            "historical",
        }:
            raise ValueError("resource temporal_semantics is invalid")


@dataclass(frozen=True, slots=True)
class ResourcePlanStep:
    capability_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    purpose: str = "retrieve governed resource data"

    def __post_init__(self) -> None:
        if not self.capability_name.strip():
            raise ValueError("capability_name is required")
        if not self.purpose.strip():
            raise ValueError("plan step purpose is required")


@dataclass(frozen=True, slots=True)
class ResourceInquiryPlan:
    steps: tuple[ResourcePlanStep, ...]
    requested_facts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise LookupError("resource inquiry plan must contain at least one governed capability")


class ResourceCapabilityReasoner(Protocol):
    """Reason about capability descriptions only; never execute providers or agents."""

    def select(
        self,
        *,
        inquiry: ResourceInquiry,
        candidates: Sequence[CapabilityDefinition],
    ) -> Sequence[ResourcePlanStep]: ...


@dataclass(frozen=True, slots=True)
class GovernedResourceInquiryPlanner:
    """Let Jason determine how to obtain information from registered resources.

    The reasoning component receives capability metadata, not provider credentials or
    connector handles. Every returned plan step is revalidated against the capability
    registry before it can become executable orchestration work.
    """

    registry: CapabilityRegistryService
    reasoner: ResourceCapabilityReasoner

    def plan(self, inquiry: ResourceInquiry) -> ResourceInquiryPlan:
        candidates = tuple(
            capability
            for capability in self.registry.list_all()
            if self._eligible(capability, inquiry)
        )
        if not candidates:
            raise LookupError("no governed read capabilities are available for this resource inquiry")

        proposed = tuple(self.reasoner.select(inquiry=inquiry, candidates=candidates))
        if not proposed:
            raise LookupError("resource capability reasoner could not produce a governed plan")

        validated: list[ResourcePlanStep] = []
        for step in proposed:
            capability = self.registry.get_current(capability_name=step.capability_name)
            if capability not in candidates:
                raise PermissionError(
                    "resource plan selected a capability outside the governed candidate set"
                )
            if inquiry.execution_mode not in capability.permitted_execution_modes:
                raise PermissionError(
                    "resource plan selected a capability that does not permit the requested execution mode"
                )
            if capability.metadata.get("provider_neutral", "false").lower() != "true":
                raise PermissionError("resource inquiry plans must use provider-neutral capabilities")
            if capability.metadata.get("read_only", "false").lower() != "true":
                raise PermissionError("resource inquiry plans may only use declared read-only capabilities")
            validated.append(step)

        return ResourceInquiryPlan(
            steps=tuple(validated),
            requested_facts=inquiry.requested_facts,
        )

    @staticmethod
    def _eligible(capability: CapabilityDefinition, inquiry: ResourceInquiry) -> bool:
        if inquiry.execution_mode not in capability.permitted_execution_modes:
            return False
        if capability.metadata.get("provider_neutral", "false").lower() != "true":
            return False
        if capability.metadata.get("read_only", "false").lower() != "true":
            return False
        resource_types = {
            item.strip()
            for item in capability.metadata.get("resource_types", "").split(",")
            if item.strip()
        }
        return inquiry.resource_type in resource_types
