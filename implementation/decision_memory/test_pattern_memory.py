from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from decision_memory.pattern_memory import AOTPatternMemoryBuilder
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


NOW = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)


def case(
    case_id: str,
    client_id: str,
    *,
    days_old: int = 1,
    failed_first_step: bool = False,
    root_cause: str = "unhealthy edr install",
    symptom: str = "service stopped",
) -> ResolutionCase:
    return ResolutionCase(
        case_id=case_id,
        organization_id="aot",
        client_id=client_id,
        signature=ResolutionSignature(
            category="endpoint security",
            product="Datto EDR AV",
            device_role="workstation",
            platform="Windows",
            product_version="3.17.1.6224",
            symptoms=(symptom, "agent unhealthy"),
            attributes={
                "service": "EndpointProtectionService",
                "hostname": f"{client_id}-PC01",
                "ip_address": "10.20.30.40",
            },
        ),
        source_references=(
            ResolutionSourceReference(
                source_type="autotask_ticket",
                source_id=f"T20260927.{100 + len(case_id)}",
                correlation_id=f"corr-{client_id}",
            ),
        ),
        steps=(
            ResolutionStep(
                step_id=f"{case_id}-s1",
                ordinal=1,
                kind=ResolutionStepKind.DIAGNOSTIC,
                action_key="datto.edr.status",
                action_summary=f"Check EDR status on {client_id}-PC01",
                outcome=(
                    ResolutionOutcome.FAILED
                    if failed_first_step
                    else ResolutionOutcome.IMPROVED
                ),
                evidence_summary=f"Ticket for {client_id}",
                read_only=True,
            ),
            ResolutionStep(
                step_id=f"{case_id}-s2",
                ordinal=2,
                kind=ResolutionStepKind.REMEDIATION,
                action_key="datto.edr.reinstall",
                action_summary=f"Reinstall EDR on {client_id}-PC01",
                outcome=ResolutionOutcome.RESOLVED,
                approval_required=True,
                disruptive=True,
            ),
        ),
        root_cause=root_cause,
        final_resolution=f"Reinstalled EDR on {client_id}-PC01",
        outcome=ResolutionOutcome.RESOLVED,
        status=ResolutionCaseStatus.VERIFIED,
        technician_confirmed=True,
        recorded_at=NOW - timedelta(days=days_old),
        resolved_at=NOW - timedelta(days=days_old),
        owner=f"tech-{client_id}",
    )


def test_two_clients_promote_sanitized_pattern_without_identity_fields(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    service = ResolutionMemoryService(store=store)
    service.initialize()
    service.record_case(case("CASE-A", "client-a"))
    assert service.pattern_store.count_patterns(organization_id="aot") == 0

    service.record_case(case("CASE-B", "client-b"))
    patterns = service.pattern_store.list_patterns(organization_id="aot")
    assert len(patterns) == 1
    projected = patterns[0].project()
    payload = json.dumps(projected, sort_keys=True).casefold()

    for forbidden in (
        "client-a",
        "client-b",
        "case-a",
        "case-b",
        "t20260927",
        "corr-",
        "pc01",
        "10.20.30.40",
        "hostname",
        "ip_address",
        "tech-client",
    ):
        assert forbidden not in payload

    assert projected["support_count"] == 2
    assert projected["supporting_client_count"] == 2
    assert projected["promotion_mode"] == "repeated_independent_cases"
    assert projected["raw_source_cases_exposed"] is False
    assert projected["grants_authority"] is False
    assert projected["steps"][1]["approval_required"] is True
    assert projected["steps"][1]["disruptive"] is True


def test_same_client_raw_case_and_other_client_pattern_retrieval_are_separate(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    service = ResolutionMemoryService(store=store)
    service.initialize()
    service.record_case(case("CASE-A", "client-a"))
    service.record_case(case("CASE-B", "client-b"))

    signature = ResolutionSignature(
        category="endpoint security",
        product="Datto EDR AV",
        device_role="workstation",
        platform="Windows",
        product_version="3.17.1.6224",
        symptoms=("service stopped", "agent unhealthy"),
        attributes={"service": "EndpointProtectionService"},
    )

    same_client = service.search_evidence(
        signature=signature,
        organization_id="aot",
        client_id="client-a",
        now=NOW,
    )
    assert [item["case_id"] for item in same_client["matches"]] == ["CASE-A"]
    assert same_client["pattern_count"] == 1

    other_client = service.search_evidence(
        signature=signature,
        organization_id="aot",
        client_id="client-c",
        now=NOW,
    )
    assert other_client["matches"] == []
    assert other_client["pattern_count"] == 1
    assert other_client["raw_cross_client_cases_exposed"] is False
    assert "CASE-A" not in json.dumps(other_client)
    assert "CASE-B" not in json.dumps(other_client)
    assert other_client["retrieval_hierarchy"][0] == "same_client_exact_or_similar"
    assert other_client["retrieval_hierarchy"][1] == "aot_sanitized_patterns"
    assert other_client["current_live_evidence_precedence"] is True


def test_failed_step_and_contradiction_reduce_pattern_confidence(tmp_path) -> None:
    clean_builder = AOTPatternMemoryBuilder()
    clean = clean_builder.derive(
        organization_id="aot",
        cases=(case("A", "client-a"), case("B", "client-b")),
        now=NOW,
    )[0]
    conflicted = clean_builder.derive(
        organization_id="aot",
        cases=(
            case("A", "client-a"),
            case("B", "client-b", failed_first_step=True),
        ),
        now=NOW,
    )[0]

    assert conflicted.contradiction_count == 1
    assert conflicted.contradiction_rate == 0.5
    assert conflicted.confidence < clean.confidence
    status_step = next(
        item for item in conflicted.steps if item.action_key == "datto.edr.status"
    )
    assert status_step.failures == 1
    assert status_step.disposition == "historically_conflicted"
    assert status_step.confidence < next(
        item for item in clean.steps if item.action_key == "datto.edr.status"
    ).confidence


def test_one_case_requires_explicit_technician_approval_for_early_promotion() -> None:
    builder = AOTPatternMemoryBuilder()
    single = case("ONLY", "client-a")
    assert builder.derive(
        organization_id="aot", cases=(single,), now=NOW
    ) == ()

    promoted = builder.derive(
        organization_id="aot",
        cases=(single,),
        now=NOW,
        technician_approved_case_ids=frozenset({"ONLY"}),
    )
    assert len(promoted) == 1
    assert promoted[0].promotion_mode == "technician_approved_early_promotion"
    assert promoted[0].supporting_client_count == 1


def test_ambiguous_identifying_material_fails_closed_for_pattern_promotion(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    service = ResolutionMemoryService(store=store)
    service.initialize()
    service.record_case(
        case(
            "CASE-A",
            "client-a",
            symptom="service stopped for user@example.com",
        )
    )
    service.record_case(
        case(
            "CASE-B",
            "client-b",
            symptom="service stopped for user@example.com",
        )
    )

    assert service.pattern_store.count_patterns(organization_id="aot") == 0
    # Raw cases remain available only to their own client scope.
    assert store.get_case(
        case_id="CASE-A", organization_id="aot", client_id="client-a"
    ) is not None
    assert store.get_case(
        case_id="CASE-A", organization_id="aot", client_id="client-b"
    ) is None


def test_pattern_evidence_never_grants_execution_authority(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    service = ResolutionMemoryService(store=store)
    service.initialize()
    service.record_case(case("CASE-A", "client-a"))
    service.record_case(case("CASE-B", "client-b"))
    result = service.search_evidence(
        signature=case("Q", "client-c").signature,
        organization_id="aot",
        client_id="client-c",
        now=NOW,
    )
    assert result["grants_authority"] is False
    assert result["execution_authority_source"] == "current_jason_governance_only"
    assert result["aot_patterns"][0]["grants_authority"] is False
    assert all(
        step["grants_authority"] is False
        for step in result["aot_patterns"][0]["steps"]
    )
