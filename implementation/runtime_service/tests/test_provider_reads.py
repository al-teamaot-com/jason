from __future__ import annotations

from datetime import datetime, timezone

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from orchestrator.integration_broker import IntegrationBroker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_TICKET_SEARCH,
)
from jason_runtime.provider_reads import (
    build_provider_read_invoker,
    register_provider_read_invokers,
    register_provider_read_runtime_foundation,
)


class _Secrets:
    def resolve(self, logical_name, context):
        raise AssertionError("source composition tests must not resolve provider secrets")


class _Transport:
    def request(self, **kwargs):
        raise AssertionError("source composition tests must not call provider APIs")


class _Audit:
    def record(self, event_type, context, details):
        return None


def test_provider_read_runtime_registers_broker_manifests_without_becoming_operational() -> None:
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    broker = IntegrationBroker(capabilities=capabilities, providers=providers)

    register_provider_read_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        integration_broker=broker,
        now=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    assert providers.get(IT_GLUE_PROVIDER).provider_id == IT_GLUE_PROVIDER
    assert providers.get(AUTOTASK_PROVIDER).provider_id == AUTOTASK_PROVIDER
    assert not broker.get(IT_GLUE_PROVIDER).operational
    assert not broker.get(AUTOTASK_PROVIDER).operational


def test_provider_read_runtime_registers_canonical_invokers_without_io() -> None:
    provider_invoker = build_provider_read_invoker(
        secrets=_Secrets(),
        transport=_Transport(),
        audit=_Audit(),
    )
    invokers = CapabilityInvokerRegistry()

    register_provider_read_invokers(invokers=invokers, invoker=provider_invoker)

    registered = set(invokers.registered_capabilities())
    assert DOCUMENTATION_ORGANIZATION_SEARCH in registered
    assert SERVICE_TICKET_SEARCH in registered
