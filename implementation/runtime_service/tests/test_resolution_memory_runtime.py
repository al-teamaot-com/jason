from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from decision_memory.resolution_memory import (
    ResolutionCase,
    ResolutionCaseStatus,
    ResolutionOutcome,
    ResolutionSignature,
    ResolutionSourceReference,
    ResolutionStep,
    ResolutionStepKind,
)
from decision_memory.resolution_service import ResolutionMemoryService
from decision_memory.resolution_sqlite import SQLiteResolutionMemoryStore
from jason_runtime.resolution_memory_runtime import (
    RESOLUTION_MEMORY_PROVIDER,
    RESOLUTION_MEMORY_READ,
    RESOLUTION_MEMORY_SEARCH,
    GovernedResolutionMemoryCapabilityInvoker,
    register_resolution_memory_runtime_foundation,
)
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest


NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def build_case() -> ResolutionCase:
    return ResolutionCase(
        case_id="CASE-1",
        organization_id="aot",
        client_id="client-a",
        signature=ResolutionSignature(
            category="endpoint security",
            product="Datto EDR AV",
            device_role="workstation",
            platform="Windows",
            product_version="3.17.1.6224",
            symptoms=("service stopped", "edr version out of date"),
            attributes={"service": "EndpointProtectionService"},
        ),
        source_references=(
            ResolutionSourceReference(
                source_type="autotask_ticket",
                source_id="T-1",
                correlation_id="corr-1",
            ),
        ),
        steps=(
            ResolutionStep(
                step_id="S-1",
                ordinal=1,
                kind=ResolutionStepKind.DIAGNOSTIC,
                action_key="datto.edr.status",
                action_summary="Check Datto EDR/AV status",
                outcome=ResolutionOutcome.IMPROVED,
                read_only=True,
            ),
            ResolutionStep(
                step_id="S-2",
                ordinal=2,
                kind=ResolutionStepKind.REMEDIATION,
                action_key="datto.edr.reinstall",
                action_summary="Reinstall Datto EDR",
                outcome=ResolutionOutcome.RESOLVED,
                approval_required=True,
                disruptive=True,
            ),
        ),
        root_cause="Unhealthy EDR install",
        final_resolution="Reinstalled EDR",
        outcome=ResolutionOutcome.RESOLVED,
        status=ResolutionCaseStatus.VERIFIED,
        technician_confirmed=True,
        recorded_at=NOW - timedelta(days=1),
        resolved_at=NOW - timedelta(days=1),
        owner="aot-tech",
    )


def request(*, capability: str, client_id: str | None, arguments: dict):
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id=client_id,
        capability_name=capability,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=OrchestrationMode.CHECK_ONLY,
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=SimpleNamespace(),
        budget=SimpleNamespace(),
        arguments=arguments,
        permission_mode="observe",
    )


def resolution(capability: str):
    return SimpleNamespace(
        selected_provider_id=RESOLUTION_MEMORY_PROVIDER,
        capability_name=capability,
    )


def test_foundation_registers_read_only_resolution_capabilities() -> None:
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    register_resolution_memory_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )

    search = capabilities.get_current(capability_name=RESOLUTION_MEMORY_SEARCH)
    read = capabilities.get_current(capability_name=RESOLUTION_MEMORY_READ)

    assert search.metadata["read_only"] == "true"
    assert search.metadata["provider_neutral"] == "true"
    assert search.metadata["authority_semantics"] == (
        "evidence_only_never_grants_execution_authority"
    )
    assert read.metadata["read_only"] == "true"


def test_search_returns_history_without_authority(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    service = ResolutionMemoryService(store=store)
    service.initialize()
    service.record_case(build_case())
    invoker = GovernedResolutionMemoryCapabilityInvoker(service=service)

    result = invoker.invoke(
        request=request(
            capability=RESOLUTION_MEMORY_SEARCH,
            client_id="client-a",
            arguments={
                "category": "endpoint security",
                "product": "Datto EDR AV",
                "device_role": "workstation",
                "platform": "Windows",
                "product_version": "3.17.1.6224",
                "symptoms": ["service stopped", "edr version out of date"],
                "attributes": {"service": "EndpointProtectionService"},
            },
        ),
        resolution=resolution(RESOLUTION_MEMORY_SEARCH),
    )

    data = result.output["data"]
    assert data["match_count"] == 1
    assert data["grants_authority"] is False
    assert data["matches"][0]["grants_authority"] is False
    assert all(item["grants_authority"] is False for item in data["step_evidence"])


def test_search_requires_current_client_scope(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    service = ResolutionMemoryService(store=store)
    service.initialize()
    invoker = GovernedResolutionMemoryCapabilityInvoker(service=service)

    try:
        invoker.invoke(
            request=request(
                capability=RESOLUTION_MEMORY_SEARCH,
                client_id=None,
                arguments={
                    "category": "endpoint security",
                    "product": "Datto EDR AV",
                    "device_role": "workstation",
                    "platform": "Windows",
                },
            ),
            resolution=resolution(RESOLUTION_MEMORY_SEARCH),
        )
    except PermissionError as exc:
        assert "current client scope" in str(exc)
    else:
        raise AssertionError("resolution memory allowed an unscoped search")


def test_read_cannot_cross_client_boundary(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    service = ResolutionMemoryService(store=store)
    service.initialize()
    service.record_case(build_case())
    invoker = GovernedResolutionMemoryCapabilityInvoker(service=service)

    try:
        invoker.invoke(
            request=request(
                capability=RESOLUTION_MEMORY_READ,
                client_id="different-client",
                arguments={"resource_id": "CASE-1"},
            ),
            resolution=resolution(RESOLUTION_MEMORY_READ),
        )
    except LookupError as exc:
        assert "current client scope" in str(exc)
    else:
        raise AssertionError("resolution memory leaked a cross-client case")
