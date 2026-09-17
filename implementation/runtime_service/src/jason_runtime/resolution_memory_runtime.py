from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from decision_memory.resolution_memory import ResolutionSignature
from decision_memory.resolution_service import ResolutionMemoryService
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
from orchestrator.contracts import OrchestrationRequest
from orchestrator.service import InvocationResult


RESOLUTION_MEMORY_SEARCH = "operations.resolution.search"
RESOLUTION_MEMORY_READ = "operations.resolution.read"
RESOLUTION_MEMORY_PROVIDER = "resolution_memory"


def _capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    operation: str,
    selector_keys: str,
    planning_guidance: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Reuse verified historical troubleshooting outcomes as bounded evidence "
            "without granting execution authority or bypassing current governance."
        ),
        owner_service="Jason Operational Resolution Memory",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-012"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=(
            f"schema://jason/{capability_name.replace('.', '-')}/1.0"
        ),
        output_schema_reference=(
            "schema://jason/operational-resolution-memory-evidence/1.0"
        ),
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=(
                "organization/client-scoped resolution memory records",
                "normalized current incident signature",
            ),
            verification_requirements=(
                "historical evidence does not grant execution authority",
                "raw similar cases remain client-isolated",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=5,
        maximum_attempts=1,
        failure_behavior=(
            "Fail closed without cross-client fallback, inferred authority, or provider action."
        ),
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Reduce repeated troubleshooting effort by reusing verified AOT operating "
                "history while preserving evidence, client isolation, and human authority."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Replaced by a broader governed institutional-memory capability with equal "
                "or stronger isolation, provenance, and no-authority guarantees.",
            ),
            authoritative_change_sources=(
                "RESMEM-001 Operational Resolution Memory",
                "REFLECT-001 Governed Reflection",
            ),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Governance Authority",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "resolution_case,resolution_memory",
            "operation": operation,
            "selector_keys": selector_keys,
            "selector_required": "true",
            "fact_hints": (
                "resolution similar historical prior case root cause fix failed worked "
                "troubleshoot troubleshooting alert ticket symptom error service product "
                "diagnostic remediation verification outcome previous recurring"
            ),
            "planning_guidance": planning_guidance,
            "authority_semantics": "evidence_only_never_grants_execution_authority",
        },
    )


def resolution_memory_search(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=RESOLUTION_MEMORY_SEARCH,
        display_name="Search Operational Resolution Memory",
        operation="search",
        selector_keys=(
            "category,product,device_role,platform,product_version,symptoms,attributes,limit"
        ),
        planning_guidance=(
            "Use after current incident facts are known to find materially similar historical "
            "cases and see which diagnostic/remediation steps succeeded or failed. Current "
            "governance remains authoritative for any action."
        ),
    )


def resolution_memory_read(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=RESOLUTION_MEMORY_READ,
        display_name="Read Operational Resolution Case",
        operation="read",
        selector_keys="resource_id,case_id",
        planning_guidance=(
            "Use to inspect one previously returned resolution case within the current client "
            "scope. Historical cases are evidence only."
        ),
    )


def resolution_memory_provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=RESOLUTION_MEMORY_PROVIDER,
        display_name="Jason Operational Resolution Memory",
        provider_type=ProviderType.DETERMINISTIC,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(
            {RESOLUTION_MEMORY_SEARCH, RESOLUTION_MEMORY_READ}
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
                "Jason's own governed resolution history is the authoritative internal provider "
                "for historical troubleshooting evidence."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "A replacement governed institutional-memory provider satisfies RESMEM-001.",
            ),
            vendor_change_sources=("RESMEM-001",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Governance Authority",
        ),
        created_at=now,
        metadata={
            "read_only": "true",
            "authoritative": "true",
            "evidence_only": "true",
            "grants_authority": "false",
        },
    )


def register_resolution_memory_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    capabilities.register(resolution_memory_search(now))
    capabilities.register(resolution_memory_read(now))
    providers.register(resolution_memory_provider(now))


@dataclass(frozen=True, slots=True)
class GovernedResolutionMemoryCapabilityInvoker:
    service: ResolutionMemoryService

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if request.permission_mode != "observe":
            raise PermissionError("resolution memory capabilities are read-only")
        if resolution.selected_provider_id != RESOLUTION_MEMORY_PROVIDER:
            raise PermissionError("resolution memory resolved to an unexpected provider")
        if request.capability_name != resolution.capability_name:
            raise ValueError("resolved resolution-memory capability does not match request")
        if not request.client_id:
            raise PermissionError("resolution memory requires current client scope")

        if resolution.capability_name == RESOLUTION_MEMORY_SEARCH:
            data = self._search(request)
        elif resolution.capability_name == RESOLUTION_MEMORY_READ:
            data = self._read(request)
        else:
            raise LookupError(
                f"unsupported resolution memory capability: {resolution.capability_name}"
            )

        return InvocationResult(
            output={
                "provider": RESOLUTION_MEMORY_PROVIDER,
                "provider_capability": resolution.capability_name,
                "data": data,
                "evidence_ids": (),
                "warnings": (),
            },
            attempts=1,
        )

    def _search(self, request: OrchestrationRequest) -> Mapping[str, Any]:
        arguments = request.arguments
        required = ("category", "product", "device_role", "platform")
        missing = [
            name
            for name in required
            if not str(arguments.get(name, "")).strip()
        ]
        if missing:
            raise ValueError(
                "resolution memory search missing required signature fields: "
                + ", ".join(missing)
            )

        symptoms_raw = arguments.get("symptoms", ())
        if isinstance(symptoms_raw, str):
            symptoms = tuple(
                item.strip()
                for item in symptoms_raw.split(",")
                if item.strip()
            )
        elif isinstance(symptoms_raw, (list, tuple)):
            symptoms = tuple(
                str(item).strip()
                for item in symptoms_raw
                if str(item).strip()
            )
        else:
            raise ValueError("resolution memory symptoms must be a string or list")

        attributes_raw = arguments.get("attributes", {})
        if attributes_raw is None:
            attributes_raw = {}
        if not isinstance(attributes_raw, Mapping):
            raise ValueError("resolution memory attributes must be an object")
        if len(attributes_raw) > 32:
            raise ValueError("resolution memory attributes exceed bounded limit")
        attributes = {
            str(key).strip(): str(value).strip()
            for key, value in attributes_raw.items()
            if str(key).strip() and str(value).strip()
        }

        limit = int(arguments.get("limit", 10) or 10)
        if limit < 1 or limit > 25:
            raise ValueError("resolution memory limit must be between 1 and 25")

        result = self.service.search_similar(
            signature=ResolutionSignature(
                category=str(arguments["category"]),
                product=str(arguments["product"]),
                device_role=str(arguments["device_role"]),
                platform=str(arguments["platform"]),
                product_version=str(arguments.get("product_version", "")),
                symptoms=symptoms,
                attributes=attributes,
            ),
            organization_id=request.organization_id,
            client_id=request.client_id,
            limit=limit,
        )
        projected = self.service.project_search_result(result)
        return {
            "match_count": len(projected["matches"]),
            **projected,
        }

    def _read(self, request: OrchestrationRequest) -> Mapping[str, Any]:
        case_id = str(
            request.arguments.get("resource_id")
            or request.arguments.get("case_id")
            or ""
        ).strip()
        if not case_id:
            raise ValueError("resolution memory read requires resource_id or case_id")

        case = self.service.store.get_case(
            case_id=case_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
        )
        if case is None:
            raise LookupError("resolution case not found in current client scope")

        return {
            "resource_id": case.case_id,
            "case_id": case.case_id,
            "signature": {
                "category": case.signature.category,
                "product": case.signature.product,
                "device_role": case.signature.device_role,
                "platform": case.signature.platform,
                "product_version": case.signature.product_version,
                "symptoms": list(case.signature.symptoms),
                "attributes": dict(case.signature.attributes),
            },
            "root_cause": case.root_cause,
            "final_resolution": case.final_resolution,
            "outcome": case.outcome.value,
            "status": case.status.value,
            "technician_confirmed": case.technician_confirmed,
            "recorded_at": case.recorded_at.isoformat(),
            "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
            "source_references": [
                {
                    "source_type": ref.source_type,
                    "source_id": ref.source_id,
                    "correlation_id": ref.correlation_id,
                }
                for ref in case.source_references
            ],
            "steps": [
                {
                    "ordinal": step.ordinal,
                    "kind": step.kind.value,
                    "action_key": step.action_key,
                    "action_summary": step.action_summary,
                    "outcome": step.outcome.value,
                    "evidence_summary": step.evidence_summary,
                    "read_only": step.read_only,
                    "approval_required": step.approval_required,
                    "disruptive": step.disruptive,
                }
                for step in sorted(case.steps, key=lambda item: item.ordinal)
            ],
            "evidence_only": True,
            "grants_authority": False,
            "execution_authority_source": "current_jason_governance_only",
        }
