from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from connectors.autotask.impersonating_connector import AutotaskImpersonatingConnector
from connectors.core.connector_base import PreparedRequest
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.provider_read_argument_adapter import (
    GovernedProviderReadConnectorInvoker,
    adapt_autotask_arguments,
)
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_TICKET_SEARCH,
)
from orchestrator.service import InvocationResult
from reflection import (
    CandidateActorKind,
    CandidateLifecycle,
    ReflectionRecord,
    ReflectionService,
    ReflectionSignalKind,
    SQLiteReflectionStore,
)
from jason_runtime.reflection_runtime import (
    REFLECTION_CANDIDATE_REVIEW,
    REFLECTION_CORRECTION_RECORD,
    REFLECTION_PROVIDER,
    GovernedReflectionCapabilityInvoker,
    ReflectionCollectingAuditSink,
)


NOW = datetime(2026, 9, 27, 18, 30, tzinfo=timezone.utc)


def request(capability: str, *, arguments: dict, permission_mode: str = "observe") -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
        capability_name=capability,
        capability_version=None,
        requested_mode="deterministic",
        orchestration_mode=(OrchestrationMode.CHECK_ONLY if permission_mode == "observe" else OrchestrationMode.EXECUTE),
        authority_allowed=True,
        approval_present=False,
        risk="low",
        data_handling=SimpleNamespace(),
        budget=SimpleNamespace(),
        arguments=arguments,
        requester_kind="human",
        permission_mode=permission_mode,
        authority_context_id="ctx-1",
    )


def resolution(capability: str, provider: str):
    return SimpleNamespace(
        selected_provider_id=provider,
        capability_name=capability,
    )


class QueueDelegate:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.requests = []

    def invoke(self, *, request, resolution):
        self.requests.append(request)
        return self.outputs.pop(0)


def itg_result(records):
    return InvocationResult(
        output={
            "provider": IT_GLUE_PROVIDER,
            "provider_capability": "it_glue.entity.query",
            "data": {"data": records, "meta": {"current-page": 1}},
        }
    )


def org(org_id: str, name: str):
    return {"id": org_id, "type": "organizations", "attributes": {"name": name}}


def test_hitt_style_name_resolution_uses_bounded_normalized_fallback() -> None:
    delegate = QueueDelegate(
        [
            itg_result([]),
            itg_result(
                [
                    org("101", "Hitt Electric Corp."),
                    org("102", "Unrelated Company"),
                ]
            ),
        ]
    )
    invoker = GovernedProviderReadConnectorInvoker(delegate=delegate)
    result = invoker.invoke(
        request=request(
            DOCUMENTATION_ORGANIZATION_SEARCH,
            arguments={"name": "Hitt Electric"},
        ),
        resolution=resolution(DOCUMENTATION_ORGANIZATION_SEARCH, IT_GLUE_PROVIDER),
    )

    records = result.output["data"]["data"]
    assert [item["id"] for item in records] == ["101"]
    assert len(delegate.requests) == 2
    assert delegate.requests[0].arguments["filters"] == {"name": "Hitt Electric"}
    assert "name" not in delegate.requests[1].arguments["filters"]
    assert delegate.requests[1].arguments["page_size"] == 1000
    assert result.telemetry is not None
    assert result.telemetry.reflection_search_strategies == (
        "exact",
        "normalized_prefix_contains",
    )
    assert result.telemetry.reflection_search_result_counts == (0, 1)
    assert result.telemetry.reflection_fallback_count == 1


def test_hitt_style_name_resolution_fails_closed_on_ambiguity() -> None:
    delegate = QueueDelegate(
        [
            itg_result([]),
            itg_result(
                [
                    org("101", "Hitt Electric Corp."),
                    org("102", "Hitt Electric Services"),
                ]
            ),
        ]
    )
    invoker = GovernedProviderReadConnectorInvoker(delegate=delegate)
    with pytest.raises(ValueError, match="IT_GLUE_ORGANIZATION_SEARCH_AMBIGUOUS"):
        invoker.invoke(
            request=request(
                DOCUMENTATION_ORGANIZATION_SEARCH,
                arguments={"name": "Hitt Electric"},
            ),
            resolution=resolution(DOCUMENTATION_ORGANIZATION_SEARCH, IT_GLUE_PROVIDER),
        )


def test_open_ticket_intent_is_pushed_down_as_internal_semantic_filter() -> None:
    adapted = adapt_autotask_arguments(
        SERVICE_TICKET_SEARCH,
        {"company_id": 42, "status": "open", "page_size": 25},
    )
    search = json.loads(adapted["search"])
    assert search["MaxRecords"] == 25
    assert {"op": "eq", "field": "companyID", "value": 42} in search["filter"]
    assert {"op": "jason_open", "field": "status", "value": "open"} in search["filter"]


class StubTransport:
    def __init__(self, metadata):
        self.metadata = metadata
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.metadata


class StubSecrets:
    def resolve(self, *args, **kwargs):
        return {}


class StubAudit:
    def record(self, *args, **kwargs):
        return None


class StubBindings:
    def resolve(self, *args, **kwargs):
        return None


def test_open_ticket_intent_resolves_live_terminal_status_to_provider_exclusion() -> None:
    transport = StubTransport(
        {
            "fields": [
                {
                    "name": "status",
                    "picklistValues": [
                        {"label": "New", "value": 1},
                        {"label": "In Progress", "value": 8},
                        {"label": "Complete", "value": 5},
                    ],
                }
            ]
        }
    )
    connector = AutotaskImpersonatingConnector(
        secrets=StubSecrets(),
        transport=transport,
        audit=StubAudit(),
        bindings=StubBindings(),
    )
    prepared = PreparedRequest(
        method="GET",
        url="https://example.autotask.net/atservicesrest/V1.0/Tickets/query",
        headers={},
        params={
            "search": json.dumps(
                {
                    "MaxRecords": 25,
                    "filter": [
                        {"op": "eq", "field": "companyID", "value": 42},
                        {"op": "jason_open", "field": "status", "value": "open"},
                    ],
                }
            )
        },
        audit_operation="/V1.0/Tickets/query",
    )
    resolved = connector._resolve_ticket_search_status(prepared=prepared)
    search = json.loads(resolved.params["search"])
    assert {"op": "jason_open", "field": "status", "value": "open"} not in search["filter"]
    assert {"op": "noteq", "field": "status", "value": 5} in search["filter"]
    assert not any(item.get("value") in {1, 8} and item.get("op") == "noteq" for item in search["filter"])
    assert len(transport.calls) == 1


def source_record(record_id: str = "source-1") -> ReflectionRecord:
    return ReflectionRecord(
        record_id=record_id,
        execution_id="exec-source",
        correlation_id="corr-source",
        organization_id="aot",
        client_id="client-1",
        capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
        provider_id=IT_GLUE_PROVIDER,
        outcome="succeeded",
        normalized_intent="organization_search",
        selector_strategy="bounded_name_resolution",
        requested_result_scope="single",
        result_count=1,
        candidate_count=1,
        provider_call_count=2,
        pagination_count=1,
        fallback_count=1,
        evidence_item_count=1,
        search_strategies=("exact", "normalized_prefix_contains"),
        search_result_counts=(0, 1),
        observed_at=NOW,
    )


def test_terminal_audit_event_is_automatically_collected_and_detected() -> None:
    store = SQLiteReflectionStore()
    service = ReflectionService(store)
    events = []

    class Audit:
        def append(self, event_type, payload):
            events.append((event_type, dict(payload)))

    sink = ReflectionCollectingAuditSink(delegate=Audit(), service=service)
    sink.append(
        "orchestration.capability.completed",
        {
            "execution_id": "exec-live",
            "correlation_id": "corr-live",
            "organization_id": "aot",
            "client_id": "client-1",
            "principal_id": "person-al",
            "capability_name": DOCUMENTATION_ORGANIZATION_SEARCH,
            "provider_id": IT_GLUE_PROVIDER,
            "stage": "completed",
            "status": "succeeded",
            "duration_ms": 12.3,
            "reflection_normalized_intent": "organization_search",
            "reflection_selector_strategy": "bounded_name_resolution",
            "reflection_requested_result_scope": "single",
            "reflection_result_count": 1,
            "reflection_candidate_count": 1,
            "reflection_provider_call_count": 2,
            "reflection_pagination_count": 1,
            "reflection_fallback_count": 1,
            "reflection_evidence_item_count": 1,
            "reflection_search_strategies": ("exact", "normalized_prefix_contains"),
            "reflection_search_result_counts": (0, 1),
            "reflection_warning_codes": ("bounded_search_broadening_used",),
        },
    )
    records = store.list_records(organization_id="aot")
    candidates = store.list_candidates(organization_id="aot")
    assert len(records) == 1
    assert len(candidates) == 1
    assert candidates[0].signal_kind is ReflectionSignalKind.SEARCH_BROADENING_SUCCESS
    assert events[0][0] == "orchestration.capability.completed"
    assert candidates[0].state is CandidateLifecycle.OBSERVED


def test_authenticated_correction_creates_audited_signal_without_authority() -> None:
    store = SQLiteReflectionStore()
    service = ReflectionService(store)
    service.observe(source_record())
    with pytest.raises(PermissionError, match="authenticated human context"):
        service.ingest_authenticated_user_correction(
            source_record_id="source-1",
            organization_id="aot",
            principal_id="person-al",
            category="provider_filter_pushdown",
            authenticated=False,
        )

    result = service.ingest_authenticated_user_correction(
        source_record_id="source-1",
        organization_id="aot",
        principal_id="person-al",
        category="provider_filter_pushdown",
        authenticated=True,
        observed_at=NOW,
    )
    assert result.correction.principal_id == "person-al"
    assert result.observation.record.user_correction_category == "provider_filter_pushdown"
    assert any(item.signal_kind is ReflectionSignalKind.USER_CORRECTION for item in result.observation.candidates)
    assert len(store.list_user_corrections(organization_id="aot")) == 1


def test_candidate_requires_ci_regression_then_human_approval_then_release_promotion() -> None:
    store = SQLiteReflectionStore()
    service = ReflectionService(store)
    observed = service.observe(source_record()).candidates[0]
    proposed = service.transition_candidate(
        candidate_key=observed.candidate_key,
        organization_id="aot",
        new_state=CandidateLifecycle.PROPOSED,
        actor_id="person-al",
        actor_kind=CandidateActorKind.HUMAN,
        reason="reviewed as generic improvement",
    )
    assert proposed.state is CandidateLifecycle.PROPOSED

    with pytest.raises(PermissionError, match="passing regression evidence"):
        store.transition_candidate(
            observed.candidate_key,
            organization_id="aot",
            new_state=CandidateLifecycle.TESTED,
            actor_id="ci:test",
            actor_kind=CandidateActorKind.CI,
            reason="attempt without durable evidence",
        )

    failed = service.record_regression_result(
        candidate_key=observed.candidate_key,
        organization_id="aot",
        test_reference="reflection-regression:negative",
        passed=False,
        actor_id="ci:reflection",
        reason="negative regression failed",
    )
    assert failed.passed is False
    assert store.get_candidate(observed.candidate_key, organization_id="aot").state is CandidateLifecycle.PROPOSED

    passed = service.record_regression_result(
        candidate_key=observed.candidate_key,
        organization_id="aot",
        test_reference="reflection-regression:bounded-name-resolution",
        passed=True,
        actor_id="ci:reflection",
        reason="bounded regression suite passed",
    )
    assert passed.passed is True
    assert store.get_candidate(observed.candidate_key, organization_id="aot").state is CandidateLifecycle.TESTED

    with pytest.raises(PermissionError, match="human governance actor"):
        service.transition_candidate(
            candidate_key=observed.candidate_key,
            organization_id="aot",
            new_state=CandidateLifecycle.APPROVED,
            actor_id="system:jason",
            actor_kind=CandidateActorKind.SYSTEM,
            reason="self approval forbidden",
        )

    approved = service.transition_candidate(
        candidate_key=observed.candidate_key,
        organization_id="aot",
        new_state=CandidateLifecycle.APPROVED,
        actor_id="person-al",
        actor_kind=CandidateActorKind.HUMAN,
        reason="human governance approval",
    )
    assert approved.state is CandidateLifecycle.APPROVED

    with pytest.raises(PermissionError, match="controlled release actor"):
        service.transition_candidate(
            candidate_key=observed.candidate_key,
            organization_id="aot",
            new_state=CandidateLifecycle.PROMOTED,
            actor_id="person-al",
            actor_kind=CandidateActorKind.HUMAN,
            reason="human cannot directly release code",
        )
    promoted = service.transition_candidate(
        candidate_key=observed.candidate_key,
        organization_id="aot",
        new_state=CandidateLifecycle.PROMOTED,
        actor_id="release:controlled",
        actor_kind=CandidateActorKind.RELEASE,
        reason="reviewed implementation merged through protected main",
    )
    assert promoted.state is CandidateLifecycle.PROMOTED
    projection = service.candidate_projection(
        candidate_key=observed.candidate_key,
        organization_id="aot",
    )
    assert projection["can_change_production"] is False
    assert projection["grants_authority"] is False
    assert len(projection["regression_evidence"]) == 2


def test_runtime_correction_and_review_reject_nonhuman_or_self_promotion() -> None:
    store = SQLiteReflectionStore()
    service = ReflectionService(store)
    service.observe(source_record())
    invoker = GovernedReflectionCapabilityInvoker(service=service)

    nonhuman = request(
        REFLECTION_CORRECTION_RECORD,
        arguments={"source_record_id": "source-1", "category": "provider_filter_pushdown"},
        permission_mode="execute",
    )
    nonhuman = SimpleNamespace(**{**nonhuman.__dict__, "requester_kind": "service"}) if hasattr(nonhuman, "__dict__") else nonhuman
    # Frozen/slots OrchestrationRequest has no __dict__; construct explicitly through replace-like helper below.
    from dataclasses import replace
    nonhuman = replace(request(
        REFLECTION_CORRECTION_RECORD,
        arguments={"source_record_id": "source-1", "category": "provider_filter_pushdown"},
        permission_mode="execute",
    ), requester_kind="service")
    with pytest.raises(PermissionError, match="human requester"):
        invoker.invoke(
            request=nonhuman,
            resolution=resolution(REFLECTION_CORRECTION_RECORD, REFLECTION_PROVIDER),
        )

    result = invoker.invoke(
        request=request(
            REFLECTION_CORRECTION_RECORD,
            arguments={"source_record_id": "source-1", "category": "provider_filter_pushdown"},
            permission_mode="execute",
        ),
        resolution=resolution(REFLECTION_CORRECTION_RECORD, REFLECTION_PROVIDER),
    )
    assert result.output["data"]["production_changed"] is False
    assert result.output["data"]["grants_authority"] is False

    candidate_key = result.output["data"]["candidate_keys"][0]
    with pytest.raises(ValueError, match="propose, approve, or reject"):
        invoker.invoke(
            request=request(
                REFLECTION_CANDIDATE_REVIEW,
                arguments={"candidate_key": candidate_key, "action": "promote", "reason": "no"},
                permission_mode="execute",
            ),
            resolution=resolution(REFLECTION_CANDIDATE_REVIEW, REFLECTION_PROVIDER),
        )
