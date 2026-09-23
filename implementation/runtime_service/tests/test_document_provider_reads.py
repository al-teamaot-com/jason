from connectors.core.contracts import ConnectorResult
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_read_capability_catalog import (
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
)
from jason_runtime.provider_reads import (
    build_provider_read_invoker,
    register_provider_read_invokers,
)


class Secrets:
    def resolve(self, logical_name, context):
        return {"api_key": "test-only"}


class Transport:
    def request(self, **kwargs):
        raise AssertionError("document runtime registration test must not perform provider IO")


class Audit:
    def record(self, event_type, context, details):
        return None


def test_runtime_registers_document_capabilities_without_provider_io() -> None:
    invoker = build_provider_read_invoker(
        secrets=Secrets(),
        transport=Transport(),
        audit=Audit(),
    )
    registry = CapabilityInvokerRegistry()
    register_provider_read_invokers(invokers=registry, invoker=invoker)

    registered = set(registry.registered_capabilities())
    assert DOCUMENTATION_DOCUMENT_SEARCH in registered
    assert DOCUMENTATION_DOCUMENT_READ in registered
