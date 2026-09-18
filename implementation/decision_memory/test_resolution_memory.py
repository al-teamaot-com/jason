from datetime import datetime, timedelta, timezone

from .resolution_memory import (
    ResolutionCase,
    ResolutionCaseStatus,
    ResolutionMemoryMatcher,
    ResolutionOutcome,
    ResolutionSignature,
    ResolutionSourceReference,
    ResolutionStep,
    ResolutionStepKind,
)
from .resolution_sqlite import SQLiteResolutionMemoryStore


NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)


def signature(*, service: str = "endpointprotectionservice") -> ResolutionSignature:
    return ResolutionSignature(
        category="endpoint security",
        product="Datto EDR AV",
        device_role="workstation",
        platform="Windows",
        product_version="3.17.1.6224",
        symptoms=(
            "EDR version out of date",
            "service stopped",
        ),
        attributes={
            "service": service,
            "agent_family": "datto-edr",
        },
    )


def case(
    case_id: str,
    *,
    client_id: str = "client-a",
    age_days: int = 5,
    outcome: ResolutionOutcome = ResolutionOutcome.RESOLVED,
    technician_confirmed: bool = True,
    steps: tuple[ResolutionStep, ...] | None = None,
) -> ResolutionCase:
    return ResolutionCase(
        case_id=case_id,
        organization_id="aot",
        client_id=client_id,
        signature=signature(),
        source_references=(
            ResolutionSourceReference(
                source_type="autotask_ticket",
                source_id=f"T-{case_id}",
                correlation_id=f"corr-{case_id}",
            ),
        ),
        steps=steps
        or (
            ResolutionStep(
                step_id=f"{case_id}-1",
                ordinal=1,
                kind=ResolutionStepKind.DIAGNOSTIC,
                action_key="datto.edr.status",
                action_summary="Check Datto EDR/AV status",
                outcome=ResolutionOutcome.IMPROVED,
                evidence_summary="Confirmed stale agent and stopped AV service",
                read_only=True,
            ),
            ResolutionStep(
                step_id=f"{case_id}-2",
                ordinal=2,
                kind=ResolutionStepKind.REMEDIATION,
                action_key="datto.edr.reinstall",
                action_summary="Reinstall and upgrade Datto EDR",
                outcome=outcome,
                evidence_summary="EDR reinstall job outcome",
                approval_required=True,
                disruptive=True,
            ),
        ),
        root_cause="Datto EDR installation unhealthy and AV service stopped",
        final_resolution="Reinstall and upgrade Datto EDR",
        outcome=outcome,
        status=ResolutionCaseStatus.VERIFIED,
        technician_confirmed=technician_confirmed,
        recorded_at=NOW - timedelta(days=age_days),
        resolved_at=NOW - timedelta(days=age_days),
        owner="aot-technician",
    )


def test_sqlite_round_trip_and_scope_isolation(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    store.initialize()
    store.add_case(case("C1", client_id="client-a"))
    store.add_case(case("C2", client_id="client-b"))

    assert store.count_cases(organization_id="aot", client_id="client-a") == 1
    assert store.count_cases(organization_id="aot", client_id="client-b") == 1

    loaded = store.get_case(
        case_id="C1",
        organization_id="aot",
        client_id="client-a",
    )
    assert loaded is not None
    assert loaded.case_id == "C1"
    assert len(loaded.steps) == 2

    # A raw case from another client is invisible even when its case ID is known.
    assert (
        store.get_case(
            case_id="C2",
            organization_id="aot",
            client_id="client-a",
        )
        is None
    )


def test_duplicate_case_fails_closed(tmp_path) -> None:
    store = SQLiteResolutionMemoryStore(str(tmp_path / "resolution.sqlite3"))
    store.initialize()
    item = case("C1")
    store.add_case(item)

    try:
        store.add_case(item)
    except ValueError as exc:
        assert "duplicate or conflicting" in str(exc)
    else:
        raise AssertionError("duplicate resolution case was accepted")


def test_similar_verified_case_returns_evidence_only() -> None:
    result = ResolutionMemoryMatcher().search(
        signature=signature(),
        organization_id="aot",
        client_id="client-a",
        cases=(case("C1"),),
        now=NOW,
    )

    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.similarity == 1.0
    assert match.evidence_only is True
    assert match.grants_authority is False
    assert result.grants_authority is False


def test_raw_similar_cases_never_cross_client_boundary() -> None:
    result = ResolutionMemoryMatcher().search(
        signature=signature(),
        organization_id="aot",
        client_id="client-a",
        cases=(
            case("C1", client_id="client-b"),
            case("C2", client_id="client-a"),
        ),
        now=NOW,
    )

    assert [item.case_id for item in result.matches] == ["C2"]


def test_recent_verified_case_ranks_above_stale_equivalent_case() -> None:
    result = ResolutionMemoryMatcher().search(
        signature=signature(),
        organization_id="aot",
        client_id="client-a",
        cases=(
            case("OLD", age_days=300),
            case("NEW", age_days=3),
        ),
        now=NOW,
    )

    assert [item.case_id for item in result.matches] == ["NEW", "OLD"]
    assert result.matches[0].score > result.matches[1].score


def test_repeated_failed_step_is_preserved_as_unreliable_evidence() -> None:
    failed_steps_1 = (
        ResolutionStep(
            step_id="F1-1",
            ordinal=1,
            kind=ResolutionStepKind.DIAGNOSTIC,
            action_key="datto.edr.status",
            action_summary="Check Datto EDR/AV status",
            outcome=ResolutionOutcome.IMPROVED,
            read_only=True,
        ),
        ResolutionStep(
            step_id="F1-2",
            ordinal=2,
            kind=ResolutionStepKind.REMEDIATION,
            action_key="windows.service.start.endpointprotectionservice",
            action_summary="Start EndpointProtectionService",
            outcome=ResolutionOutcome.FAILED,
            approval_required=True,
        ),
    )
    failed_steps_2 = (
        ResolutionStep(
            step_id="F2-1",
            ordinal=1,
            kind=ResolutionStepKind.REMEDIATION,
            action_key="windows.service.start.endpointprotectionservice",
            action_summary="Start EndpointProtectionService",
            outcome=ResolutionOutcome.FAILED,
            approval_required=True,
        ),
    )

    result = ResolutionMemoryMatcher().search(
        signature=signature(),
        organization_id="aot",
        client_id="client-a",
        cases=(
            case("F1", outcome=ResolutionOutcome.FAILED, steps=failed_steps_1),
            case("F2", outcome=ResolutionOutcome.FAILED, steps=failed_steps_2),
            case("R1"),
            case("R2"),
        ),
        now=NOW,
    )

    service_start = next(
        item
        for item in result.step_evidence
        if item.action_key
        == "windows.service.start.endpointprotectionservice"
    )
    assert service_start.attempts == 2
    assert service_start.failures == 2
    assert service_start.disposition == "historically_unreliable"
    assert service_start.grants_authority is False

    reinstall = next(
        item
        for item in result.step_evidence
        if item.action_key == "datto.edr.reinstall"
    )
    assert reinstall.successes == 2
    assert reinstall.disposition == "historically_supported"
    assert reinstall.approval_required is True
    assert reinstall.disruptive is True
    assert reinstall.grants_authority is False


def test_read_only_supported_diagnostic_sorts_before_remediation() -> None:
    result = ResolutionMemoryMatcher().search(
        signature=signature(),
        organization_id="aot",
        client_id="client-a",
        cases=(case("R1"), case("R2"), case("R3")),
        now=NOW,
    )

    supported = [
        item
        for item in result.step_evidence
        if item.disposition == "historically_supported"
    ]
    assert supported[0].action_key == "datto.edr.status"
    assert supported[0].read_only is True
    assert any(item.action_key == "datto.edr.reinstall" for item in supported)


def test_old_cases_outside_retention_window_are_ignored() -> None:
    result = ResolutionMemoryMatcher(maximum_age_days=365).search(
        signature=signature(),
        organization_id="aot",
        client_id="client-a",
        cases=(case("STALE", age_days=500),),
        now=NOW,
    )
    assert result.matches == ()
    assert result.step_evidence == ()
