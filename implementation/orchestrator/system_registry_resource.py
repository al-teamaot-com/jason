from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from kernel.resolution import CapabilityResolutionResult
from kernel.system_registry import InMemorySystemRegistry
from kernel.system_registry.manifest import registry_from_manifest

from .contracts import OrchestrationRequest
from .service import InvocationResult


SYSTEM_REGISTRY_SEARCH = "system.registry.search"
SYSTEM_REGISTRY_READ = "system.registry.read"
SYSTEM_REGISTRY_TRACE = "system.registry.trace"
SYSTEM_REGISTRY_PROVIDER = "system_registry"

_SYSTEM_REGISTRY_DIR = Path(__file__).resolve().parents[1] / "kernel" / "system_registry"
PRODUCTION_SYSTEM_REGISTRY_MANIFEST = _SYSTEM_REGISTRY_DIR / "production-registry.json"
PRODUCTION_SYSTEM_REGISTRY_LIFECYCLE = _SYSTEM_REGISTRY_DIR / "production-lifecycle-events.json"


def load_production_system_registry() -> InMemorySystemRegistry:
    return registry_from_manifest(
        PRODUCTION_SYSTEM_REGISTRY_MANIFEST,
        lifecycle_events_path=PRODUCTION_SYSTEM_REGISTRY_LIFECYCLE,
    )


def system_registry_search(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=SYSTEM_REGISTRY_SEARCH,
        display_name="Search Jason System Registry",
        business_purpose=(
            "Locate registered Jason operational entities from authoritative System Registry "
            "state without consulting conversation memory or ad hoc files."
        ),
        selector_keys="name,registry_id,entity_type,environment,lifecycle,query",
        operation="search",
        planning_guidance=(
            "Use when the human names or describes a component, capability, provider, "
            "identity binding, governance gate, credential reference, or deployment but "
            "does not already provide its durable registry resource_id."
        ),
    )


def system_registry_read(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=SYSTEM_REGISTRY_READ,
        display_name="Read Jason System Registry Entity",
        business_purpose=(
            "Read one registered Jason operational entity by durable System Registry ID."
        ),
        selector_keys="resource_id",
        operation="read",
        planning_guidance=(
            "Use when the human supplies a durable System Registry resource_id such as "
            "component.jason-runtime or provider.datto-rmm."
        ),
    )


def system_registry_trace(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=SYSTEM_REGISTRY_TRACE,
        display_name="Trace Jason System Registry Topology",
        business_purpose=(
            "Trace governed dependency relationships between two registered Jason "
            "operational entities."
        ),
        selector_keys="from,to",
        operation="trace",
        planning_guidance=(
            "Use when the human asks how two named Jason components, capabilities, "
            "providers, identities, governance gates, or deployments are connected."
        ),
    )


def _capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    business_purpose: str,
    selector_keys: str,
    operation: str,
    planning_guidance: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=business_purpose,
        owner_service="Jason System Registry",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}/1.0",
        output_schema_reference="schema://jason/system-registry-resource-record/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "authoritative System Registry record",
                "effective lifecycle derived from governed lifecycle history",
            ),
            verification_requirements=(
                "result is derived only from registered System Registry state",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=5,
        maximum_attempts=1,
        failure_behavior="Fail closed without inferred topology or conversation-memory fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Make Jason's authoritative operational topology directly queryable through "
                "the same governed capability/resource architecture used for other resources."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a broader governed System Registry resource interface.",
            ),
            authoritative_change_sources=("J-103 Jason System Registry",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "system_registry",
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": (
                "topology dependency dependencies dependent dependents transitive impact "
                "status lifecycle verified verification evidence authority governance owner "
                "steward provider capability identity deployment component configuration "
                "declared state version connection connected path trace"
            ),
            "planning_guidance": planning_guidance,
        },
    )


def system_registry_provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=SYSTEM_REGISTRY_PROVIDER,
        display_name="Jason System Registry",
        provider_type=ProviderType.DETERMINISTIC,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(
            {SYSTEM_REGISTRY_SEARCH, SYSTEM_REGISTRY_READ, SYSTEM_REGISTRY_TRACE}
        ),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=50,
            maximum_requests_per_minute=600,
            maximum_execution_seconds=5,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "The System Registry itself is the authoritative internal provider for "
                "Jason operational topology and state."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "A replacement authoritative operational-state provider satisfies J-103.",
            ),
            vendor_change_sources=("J-103 Jason System Registry",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "resource_authority": "jason_operational_state",
            "read_only": "true",
            "authoritative": "true",
        },
    )


def register_system_registry_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    capabilities.register(system_registry_search(now))
    capabilities.register(system_registry_read(now))
    capabilities.register(system_registry_trace(now))
    providers.register(system_registry_provider(now))


@dataclass(frozen=True, slots=True)
class GovernedSystemRegistryCapabilityInvoker:
    """Read authoritative System Registry state after governed provider resolution.

    This invoker has no mutation path. It cannot alter declared state, lifecycle events,
    evidence, production services, or credentials. Provider selection remains owned by
    the Central Orchestrator and capability-resolution engine.
    """

    registry: InMemorySystemRegistry

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if request.permission_mode != "observe":
            raise PermissionError("System Registry resource capabilities are read-only")
        if resolution.selected_provider_id != SYSTEM_REGISTRY_PROVIDER:
            raise PermissionError("System Registry capability resolved to an unexpected provider")
        if request.capability_name != resolution.capability_name:
            raise ValueError("resolved System Registry capability does not match request")

        if resolution.capability_name == SYSTEM_REGISTRY_SEARCH:
            data = self._search(request.arguments)
        elif resolution.capability_name == SYSTEM_REGISTRY_READ:
            data = self._read(request.arguments)
        elif resolution.capability_name == SYSTEM_REGISTRY_TRACE:
            data = self._trace(request.arguments)
        else:
            raise LookupError(
                f"unsupported System Registry capability: {resolution.capability_name}"
            )

        return InvocationResult(
            output={
                "provider": SYSTEM_REGISTRY_PROVIDER,
                "provider_capability": resolution.capability_name,
                "data": data,
                "evidence_ids": (),
                "warnings": (),
            },
            attempts=1,
        )

    def _search(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        allowed = {"name", "registry_id", "entity_type", "environment", "lifecycle", "query"}
        selectors = {
            str(key): str(value).strip()
            for key, value in arguments.items()
            if key in allowed and str(value).strip()
        }
        if not selectors:
            raise ValueError("System Registry search requires a grounded selector")

        matches = [entity for entity in self.registry.list_all() if self._matches(entity, selectors)]
        return {
            "match_count": len(matches),
            "resource_matches": [self._record(entity) for entity in matches],
        }

    def _read(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        registry_id = str(arguments.get("resource_id", "")).strip()
        if not registry_id:
            raise ValueError("System Registry read requires resource_id")
        return self._record(self.registry.get(registry_id))

    def _trace(self, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        source = self._resolve_reference(str(arguments.get("from", "")).strip())
        target = self._resolve_reference(str(arguments.get("to", "")).strip())
        path = self._shortest_relationship_path(source.registry_id, target.registry_id)
        if not path:
            raise LookupError(
                f"no registered dependency relationship path connects {source.registry_id} and {target.registry_id}"
            )

        steps: list[Mapping[str, str]] = []
        for left_id, right_id in zip(path, path[1:]):
            left = self.registry.get(left_id)
            if right_id in left.dependencies:
                relationship = "depends_on"
            else:
                relationship = "depended_on_by"
            steps.append({"from": left_id, "relationship": relationship, "to": right_id})

        return {
            "from": source.registry_id,
            "to": target.registry_id,
            "path": path,
            "relationship_steps": steps,
        }

    def _resolve_reference(self, value: str):
        if not value:
            raise ValueError("System Registry topology trace requires both from and to")
        try:
            return self.registry.get(value)
        except LookupError:
            pass

        exact = [
            entity
            for entity in self.registry.list_all()
            if entity.display_name.casefold() == value.casefold()
        ]
        if len(exact) == 1:
            return exact[0]

        partial = [
            entity
            for entity in self.registry.list_all()
            if value.casefold() in entity.display_name.casefold()
            or value.casefold() in entity.registry_id.casefold()
        ]
        if len(partial) != 1:
            raise LookupError(
                f"System Registry reference is ambiguous or unknown: {value}"
            )
        return partial[0]

    def _record(self, entity) -> Mapping[str, Any]:
        latest = self.registry.latest_verification(entity.registry_id)
        return {
            "resource_id": entity.registry_id,
            "registry_id": entity.registry_id,
            "display_name": entity.display_name,
            "entity_type": entity.entity_type.value,
            "environment": entity.environment,
            "lifecycle_status": entity.lifecycle_status.value,
            "declared_state": dict(entity.declared_state),
            "dependencies": sorted(entity.dependencies),
            "dependents": [item.registry_id for item in self.registry.dependents_of(entity.registry_id)],
            "transitive_dependencies": self._transitive_dependencies(entity.registry_id),
            "transitive_dependents": self._transitive_dependents(entity.registry_id),
            "verification_methods": list(entity.verification_methods),
            "verification_status": (
                latest.outcome.value if latest is not None else "unverified"
            ),
            "verification_evidence": (
                list(latest.evidence_references) if latest is not None else []
            ),
            "authority_references": list(entity.authority_references),
            "evidence_references": list(entity.evidence_references),
            "credential_references": [
                {"provider": item.provider, "reference": item.reference}
                for item in entity.credential_references
            ],
            "steward": entity.steward,
            "source_version": entity.source_version,
        }

    def _matches(self, entity, selectors: Mapping[str, str]) -> bool:
        for key, value in selectors.items():
            wanted = value.casefold()
            if key == "name" and wanted not in entity.display_name.casefold() and wanted not in entity.registry_id.casefold():
                return False
            if key == "registry_id" and wanted != entity.registry_id.casefold():
                return False
            if key == "entity_type" and self._singular(wanted) != entity.entity_type.value.casefold():
                return False
            if key == "environment" and wanted != entity.environment.casefold():
                return False
            if key == "lifecycle" and wanted != entity.lifecycle_status.value.casefold():
                return False
            if key == "query":
                haystack = " ".join(
                    (
                        entity.registry_id,
                        entity.display_name,
                        entity.entity_type.value,
                        entity.environment,
                        entity.lifecycle_status.value,
                    )
                ).casefold()
                if wanted not in haystack:
                    return False
        return True

    @staticmethod
    def _singular(value: str) -> str:
        aliases = {
            "components": "component",
            "capabilities": "capability",
            "providers": "provider",
            "resources": "resource",
            "deployments": "deployment",
            "identity_bindings": "identity_binding",
            "governance_gates": "governance_gate",
            "credential_references": "credential_reference",
        }
        return aliases.get(value, value)

    def _transitive_dependencies(self, registry_id: str) -> list[str]:
        return self._walk(
            seed=registry_id,
            neighbors=lambda item: self.registry.get(item).dependencies,
        )

    def _transitive_dependents(self, registry_id: str) -> list[str]:
        return self._walk(
            seed=registry_id,
            neighbors=lambda item: (
                entity.registry_id for entity in self.registry.dependents_of(item)
            ),
        )

    def _walk(self, *, seed: str, neighbors) -> list[str]:
        visited: set[str] = {seed}
        pending = deque([seed])
        found: list[str] = []
        while pending:
            current = pending.popleft()
            for candidate in sorted(neighbors(current)):
                if candidate in visited:
                    continue
                visited.add(candidate)
                found.append(candidate)
                pending.append(candidate)
        return found

    def _shortest_relationship_path(self, source: str, target: str) -> list[str]:
        if source == target:
            return [source]
        pending = deque([[source]])
        visited = {source}
        while pending:
            path = pending.popleft()
            current = path[-1]
            neighbors = set(self.registry.get(current).dependencies)
            neighbors.update(
                entity.registry_id for entity in self.registry.dependents_of(current)
            )
            for candidate in sorted(neighbors):
                if candidate in visited:
                    continue
                next_path = [*path, candidate]
                if candidate == target:
                    return next_path
                visited.add(candidate)
                pending.append(next_path)
        return []
