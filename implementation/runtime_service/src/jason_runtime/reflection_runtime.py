from __future__ import annotations

from dataclasses import dataclass, replace as dataclass_replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Protocol

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
from reflection import (
    CandidateActorKind,
    CandidateLifecycle,
    ReflectionRecord,
    ReflectionService,
)


REFLECTION_PROVIDER = "reflection_memory"
REFLECTION_SUMMARY = "operations.reflection.summary"
REFLECTION_CANDIDATE_SEARCH = "operations.reflection.candidate.search"
REFLECTION_CANDIDATE_READ = "operations.reflection.candidate.read"
REFLECTION_CORRECTION_RECORD = "operations.reflection.correction.record"
REFLECTION_CANDIDATE_REVIEW = "operations.reflection.candidate.review"

_TERMINAL_EVENTS = frozenset(
    {
        "orchestration.capability.completed",
        "orchestration.capability.failed",
        "orchestration.request.terminated",
        "orchestration.authority_context.denied",
        "orchestration.execution_plan.denied",
    }
)


class AuditSink(Protocol):
    def append(self, event_type: str, payload: Mapping[str, Any]) -> None: ...


def _capability(
    *,
    now: datetime,
    capability_name: str,
    display_name: str,
    operation: str,
    selector_keys: str,
    read_only: bool,
) -> CapabilityDefinition:
    capability = CapabilityDefinition(
        capability_name=capability_name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Observe governed execution-quality signals and maintain human-reviewed "
            "continuous-improvement candidates without changing production authority."
        ),
        owner_service="Jason Governed Reflection",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-012"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{capability_name.replace('.', '-')}/1.0",
        output_schema_reference="schema://jason/governed-reflection/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("bounded reflection record or candidate state",),
            verification_requirements=(
                "reflection cannot change code, provider access, policy, permission, or execution authority",
                "candidate approval requires human governance",
                "tested state requires durable passing CI regression evidence",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=5,
        maximum_attempts=1,
        failure_behavior="Fail closed without production change or authority expansion.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Turn repeated execution inefficiency and authenticated technician correction "
                "into auditable review candidates instead of silent recurring defects."
            ),
            review_interval_days=30,
            retirement_criteria=(
                "Replaced by a stronger governed learning subsystem with equivalent or better review, regression, and authority boundaries.",
            ),
            authoritative_change_sources=("REFLECT-001",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Governance Authority",
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true" if read_only else "false",
            "resource_types": "reflection_record,improvement_candidate,regression_evidence",
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": "reflection learning improvement correction regression candidate execution quality",
            "planning_guidance": (
                "Reflection is evidence and governance metadata only. It cannot authorize provider actions or edit production behavior."
            ),
            "authority_semantics": "never_grants_execution_authority",
        },
    )
    return capability


def reflection_summary(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=REFLECTION_SUMMARY,
        display_name="Summarize Governed Reflection",
        operation="summary",
        selector_keys="none",
        read_only=True,
    )


def reflection_candidate_search(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=REFLECTION_CANDIDATE_SEARCH,
        display_name="Search Reflection Candidates",
        operation="search",
        selector_keys="state,limit",
        read_only=True,
    )


def reflection_candidate_read(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=REFLECTION_CANDIDATE_READ,
        display_name="Read Reflection Candidate",
        operation="read",
        selector_keys="candidate_key,resource_id",
        read_only=True,
    )


def reflection_correction_record(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=REFLECTION_CORRECTION_RECORD,
        display_name="Record Authenticated Reflection Correction",
        operation="record_correction",
        selector_keys="source_record_id,category",
        read_only=False,
    )


def reflection_candidate_review(now: datetime) -> CapabilityDefinition:
    return _capability(
        now=now,
        capability_name=REFLECTION_CANDIDATE_REVIEW,
        display_name="Review Reflection Candidate",
        operation="review",
        selector_keys="candidate_key,action,reason",
        read_only=False,
    )


def reflection_provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=REFLECTION_PROVIDER,
        display_name="Jason Governed Reflection Memory",
        provider_type=ProviderType.DETERMINISTIC,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(
            {
                REFLECTION_SUMMARY,
                REFLECTION_CANDIDATE_SEARCH,
                REFLECTION_CANDIDATE_READ,
                REFLECTION_CORRECTION_RECORD,
                REFLECTION_CANDIDATE_REVIEW,
            }
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
            business_justification="Durable governed reflection is maintained by Jason itself.",
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=("A replacement governed reflection provider satisfies REFLECT-001.",),
            vendor_change_sources=("REFLECT-001",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Governance Authority",
        ),
        created_at=now,
        metadata={
            "authoritative": "true",
            "grants_authority": "false",
            "self_modifying": "false",
        },
    )


def register_reflection_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    capabilities.register(reflection_summary(now))
    capabilities.register(reflection_candidate_search(now))
    capabilities.register(reflection_candidate_read(now))
    capabilities.register(reflection_correction_record(now))
    capabilities.register(reflection_candidate_review(now))
    providers.register(reflection_provider(now))


@dataclass(frozen=True, slots=True)
class ReflectionCollectingAuditSink:
    """Mirror terminal orchestration metadata into durable Reflection Memory.

    The primary audit event is always written first. Reflection collection is a
    secondary evidence path and cannot change the outcome of the governed action.
    Collection failures are recorded back to the primary audit stream without
    recursively invoking reflection.
    """

    delegate: AuditSink
    service: ReflectionService

    def append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self.delegate.append(event_type, payload)
        if event_type not in _TERMINAL_EVENTS:
            return
        capability = str(
            payload.get("capability_name") or payload.get("capability") or ""
        ).strip()
        if not capability or capability.startswith("operations.reflection."):
            return
        execution_id = str(payload.get("execution_id") or "").strip()
        correlation_id = str(payload.get("correlation_id") or "").strip()
        organization_id = str(payload.get("organization_id") or "").strip()
        if not execution_id or not correlation_id or not organization_id:
            return

        material = f"{organization_id}|{execution_id}|{capability}"
        record_id = "reflection-" + sha256(material.encode("utf-8")).hexdigest()[:24]
        try:
            record = ReflectionRecord(
                record_id=record_id,
                execution_id=execution_id,
                correlation_id=correlation_id,
                organization_id=organization_id,
                client_id=(str(payload.get("client_id")).strip() if payload.get("client_id") is not None else None),
                capability_name=capability,
                provider_id=(str(payload.get("provider_id")).strip() if payload.get("provider_id") is not None else None),
                outcome=str(payload.get("status") or payload.get("stage") or "unknown").strip(),
                normalized_intent=str(payload.get("reflection_normalized_intent") or "").strip(),
                selector_strategy=str(payload.get("reflection_selector_strategy") or "").strip(),
                requested_result_scope=str(payload.get("reflection_requested_result_scope") or "unknown").strip(),
                result_count=_optional_int(payload.get("reflection_result_count")),
                candidate_count=_optional_int(payload.get("reflection_candidate_count")),
                provider_call_count=_int_default(payload.get("reflection_provider_call_count"), 0),
                pagination_count=_int_default(payload.get("reflection_pagination_count"), 0),
                fallback_count=_int_default(payload.get("reflection_fallback_count"), 0),
                evidence_item_count=_int_default(payload.get("reflection_evidence_item_count"), 0),
                duration_ms=_optional_float(payload.get("duration_ms")),
                search_strategies=_bounded_text_tuple(payload.get("reflection_search_strategies")),
                search_result_counts=_int_tuple(payload.get("reflection_search_result_counts")),
                warning_codes=_bounded_text_tuple(payload.get("reflection_warning_codes")),
                observed_at=datetime.now(timezone.utc),
            )
            self.service.observe(record)
        except ValueError as exc:
            if "already exists" in str(exc):
                return
            self.delegate.append(
                "reflection.collection.failed",
                {
                    "execution_id": execution_id,
                    "correlation_id": correlation_id,
                    "organization_id": organization_id,
                    "client_id": payload.get("client_id"),
                    "principal_id": payload.get("principal_id"),
                    "capability_name": capability,
                    "stage": "completed",
                    "error_code": type(exc).__name__,
                },
            )
        except Exception as exc:  # reflection must never rewrite provider outcome
            self.delegate.append(
                "reflection.collection.failed",
                {
                    "execution_id": execution_id,
                    "correlation_id": correlation_id,
                    "organization_id": organization_id,
                    "client_id": payload.get("client_id"),
                    "principal_id": payload.get("principal_id"),
                    "capability_name": capability,
                    "stage": "completed",
                    "error_code": type(exc).__name__,
                },
            )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    return int(value)


def _int_default(value: object, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    return float(value)


def _bounded_text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _int_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(int(item) for item in value)


@dataclass(frozen=True, slots=True)
class GovernedReflectionCapabilityInvoker:
    service: ReflectionService

    def invoke(
        self,
        *,
        request: OrchestrationRequest,
        resolution: CapabilityResolutionResult,
    ) -> InvocationResult:
        if resolution.selected_provider_id != REFLECTION_PROVIDER:
            raise PermissionError("reflection capability resolved to an unexpected provider")
        if request.capability_name != resolution.capability_name:
            raise ValueError("resolved reflection capability does not match request")

        if resolution.capability_name == REFLECTION_SUMMARY:
            self._require_observe(request)
            data = self.service.summary(organization_id=request.organization_id)
        elif resolution.capability_name == REFLECTION_CANDIDATE_SEARCH:
            self._require_observe(request)
            data = self._search(request)
        elif resolution.capability_name == REFLECTION_CANDIDATE_READ:
            self._require_observe(request)
            data = self._read(request)
        elif resolution.capability_name == REFLECTION_CORRECTION_RECORD:
            self._require_authenticated_human_write(request)
            data = self._record_correction(request)
        elif resolution.capability_name == REFLECTION_CANDIDATE_REVIEW:
            self._require_authenticated_human_write(request)
            data = self._review(request)
        else:
            raise LookupError(f"unsupported reflection capability: {resolution.capability_name}")

        return InvocationResult(
            output={
                "provider": REFLECTION_PROVIDER,
                "provider_capability": resolution.capability_name,
                "data": data,
                "evidence_ids": (),
                "warnings": (),
            },
            attempts=1,
        )

    @staticmethod
    def _require_observe(request: OrchestrationRequest) -> None:
        if request.permission_mode != "observe":
            raise PermissionError("reflection read capabilities are observe-only")

    @staticmethod
    def _require_authenticated_human_write(request: OrchestrationRequest) -> None:
        if request.requester_kind != "human":
            raise PermissionError("reflection correction/review requires a human requester")
        if request.permission_mode not in {"execute", "administer"}:
            raise PermissionError("reflection correction/review requires execute/administer permission")
        if not request.authority_allowed or not str(request.authority_context_id or "").strip():
            raise PermissionError("reflection correction/review requires authenticated authority context")

    def _search(self, request: OrchestrationRequest) -> Mapping[str, Any]:
        state_raw = str(request.arguments.get("state") or "").strip().casefold()
        state = CandidateLifecycle(state_raw) if state_raw else None
        limit = int(request.arguments.get("limit", 100) or 100)
        items = self.service.list_candidate_projections(
            organization_id=request.organization_id,
            state=state,
            limit=limit,
        )
        return {
            "candidates": list(items),
            "count": len(items),
            "grants_authority": False,
        }

    def _read(self, request: OrchestrationRequest) -> Mapping[str, Any]:
        candidate_key = str(
            request.arguments.get("candidate_key")
            or request.arguments.get("resource_id")
            or ""
        ).strip()
        if not candidate_key:
            raise ValueError("reflection candidate read requires candidate_key or resource_id")
        return self.service.candidate_projection(
            candidate_key=candidate_key,
            organization_id=request.organization_id,
        )

    def _record_correction(self, request: OrchestrationRequest) -> Mapping[str, Any]:
        source_record_id = str(request.arguments.get("source_record_id") or "").strip()
        category = str(request.arguments.get("category") or "").strip()
        if not source_record_id or not category:
            raise ValueError("reflection correction requires source_record_id and category")
        result = self.service.ingest_authenticated_user_correction(
            source_record_id=source_record_id,
            organization_id=request.organization_id,
            principal_id=request.principal_id,
            category=category,
            authenticated=True,
        )
        return {
            "correction_id": result.correction.correction_id,
            "correction_record_id": result.correction.correction_record_id,
            "candidate_keys": [item.candidate_key for item in result.observation.candidates],
            "production_changed": False,
            "grants_authority": False,
        }

    def _review(self, request: OrchestrationRequest) -> Mapping[str, Any]:
        candidate_key = str(request.arguments.get("candidate_key") or "").strip()
        action = str(request.arguments.get("action") or "").strip().casefold()
        reason = str(request.arguments.get("reason") or "").strip()
        if not candidate_key or not action or not reason:
            raise ValueError("reflection candidate review requires candidate_key, action, and reason")
        targets = {
            "propose": CandidateLifecycle.PROPOSED,
            "approve": CandidateLifecycle.APPROVED,
            "reject": CandidateLifecycle.REJECTED,
        }
        if action not in targets:
            raise ValueError("human reflection review action must be propose, approve, or reject")
        candidate = self.service.transition_candidate(
            candidate_key=candidate_key,
            organization_id=request.organization_id,
            new_state=targets[action],
            actor_id=request.principal_id,
            actor_kind=CandidateActorKind.HUMAN,
            reason=reason,
        )
        return {
            "candidate_key": candidate.candidate_key,
            "state": candidate.state.value,
            "production_changed": False,
            "grants_authority": False,
        }
