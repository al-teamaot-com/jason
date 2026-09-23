from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.system_registry_resource import (
    GovernedSystemRegistryCapabilityInvoker,
    SYSTEM_REGISTRY_PROVIDER,
    SYSTEM_REGISTRY_READ,
    SYSTEM_REGISTRY_SEARCH,
    SYSTEM_REGISTRY_TRACE,
    load_production_system_registry,
    register_system_registry_resource_foundation,
)


@dataclass(frozen=True)
class Resolution:
    capability_name: str
    selected_provider_id: str | None = SYSTEM_REGISTRY_PROVIDER


def request(capability_name: str, arguments, *, permission_mode: str = "observe"):
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="aot",
        capability_name=capability_name,
        capability_version="1.0",
        requested_mode="deterministic",
        permission_mode=permission_mode,
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
        ),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
        arguments=arguments,
    )


def test_foundation_registers_generic_search_read_trace_and_internal_provider():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())

    register_system_registry_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    assert capabilities.get_current(capability_name=SYSTEM_REGISTRY_SEARCH).metadata["operation"] == "search"
    assert capabilities.get_current(capability_name=SYSTEM_REGISTRY_READ).metadata["operation"] == "read"
    assert capabilities.get_current(capability_name=SYSTEM_REGISTRY_TRACE).metadata["operation"] == "trace"
    provider = providers.get(SYSTEM_REGISTRY_PROVIDER)
    assert provider.metadata["authoritative"] == "true"
    assert provider.capabilities == frozenset(
        {SYSTEM_REGISTRY_SEARCH, SYSTEM_REGISTRY_READ, SYSTEM_REGISTRY_TRACE}
    )


def test_read_returns_authoritative_dependencies_and_effective_lifecycle():
    invoker = GovernedSystemRegistryCapabilityInvoker(load_production_system_registry())

    result = invoker.invoke(
        request=request(
            SYSTEM_REGISTRY_READ,
            {"resource_id": "component.jason-runtime", "requested_facts": ("dependencies",)},
        ),
        resolution=Resolution(SYSTEM_REGISTRY_READ),  # type: ignore[arg-type]
    )

    data = result.output["data"]
    assert data["registry_id"] == "component.jason-runtime"
    assert data["lifecycle_status"] == "verified"
    assert "component.openbao" in data["dependencies"]
    assert data["verification_status"] == "verified"


def test_search_uses_registered_human_name_without_memory_fallback():
    invoker = GovernedSystemRegistryCapabilityInvoker(load_production_system_registry())

    result = invoker.invoke(
        request=request(
            SYSTEM_REGISTRY_SEARCH,
            {"name": "Jason Runtime Service", "requested_facts": ("lifecycle status",)},
        ),
        resolution=Resolution(SYSTEM_REGISTRY_SEARCH),  # type: ignore[arg-type]
    )

    data = result.output["data"]
    assert data["match_count"] == 1
    assert data["resource_matches"][0]["resource_id"] == "component.jason-runtime"


def test_trace_finds_relationship_path_without_mutating_registry():
    registry = load_production_system_registry()
    before = tuple(registry.list_all())
    invoker = GovernedSystemRegistryCapabilityInvoker(registry)

    result = invoker.invoke(
        request=request(
            SYSTEM_REGISTRY_TRACE,
            {
                "from": "component.openclaw-jason-bridge",
                "to": "provider.datto-rmm",
                "requested_facts": ("path",),
            },
        ),
        resolution=Resolution(SYSTEM_REGISTRY_TRACE),  # type: ignore[arg-type]
    )

    data = result.output["data"]
    assert data["path"][0] == "component.openclaw-jason-bridge"
    assert data["path"][-1] == "provider.datto-rmm"
    assert "component.jason-runtime" in data["path"]
    assert tuple(registry.list_all()) == before


def test_invoker_fails_closed_for_non_observe_authority_mode():
    invoker = GovernedSystemRegistryCapabilityInvoker(load_production_system_registry())

    with pytest.raises(PermissionError, match="read-only"):
        invoker.invoke(
            request=request(
                SYSTEM_REGISTRY_READ,
                {"resource_id": "component.jason-runtime"},
                permission_mode="execute",
            ),
            resolution=Resolution(SYSTEM_REGISTRY_READ),  # type: ignore[arg-type]
        )


def test_invoker_rejects_unexpected_provider_resolution():
    invoker = GovernedSystemRegistryCapabilityInvoker(load_production_system_registry())

    with pytest.raises(PermissionError, match="unexpected provider"):
        invoker.invoke(
            request=request(
                SYSTEM_REGISTRY_READ,
                {"resource_id": "component.jason-runtime"},
            ),
            resolution=Resolution(
                SYSTEM_REGISTRY_READ,
                selected_provider_id="other_provider",
            ),  # type: ignore[arg-type]
        )
