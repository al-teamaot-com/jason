import pytest

from jason_cap_004 import OperationalBriefingService, OperationalSignal


def signal(*, provider: str, subject_id: str, severity: str, category: str, summary: str) -> OperationalSignal:
    return OperationalSignal(
        source_provider=provider,
        organization_id="aot",
        subject_type="company",
        subject_id=subject_id,
        subject_name=f"Company {subject_id}",
        category=category,
        severity=severity,
        summary=summary,
        recommended_action=f"Review {category}",
        evidence_reference=f"evidence://{provider}/{subject_id}/{category}",
    )


def test_critical_subject_ranks_ahead_of_medium_subject() -> None:
    briefing = OperationalBriefingService().build(
        organization_id="aot",
        signals=(
            signal(provider="autotask", subject_id="208", severity="medium", category="tickets", summary="Open work needs review"),
            signal(provider="datto-rmm", subject_id="300", severity="critical", category="endpoint", summary="Critical endpoint condition"),
        ),
    )

    assert briefing.attention_items[0].subject_id == "300"
    assert briefing.attention_items[0].highest_severity == "critical"
    assert briefing.attention_items[0].rank == 1


def test_cross_provider_corroboration_increases_priority() -> None:
    briefing = OperationalBriefingService().build(
        organization_id="aot",
        signals=(
            signal(provider="autotask", subject_id="208", severity="high", category="tickets", summary="Repeated support issues"),
            signal(provider="it-glue", subject_id="208", severity="high", category="documentation", summary="Documentation gap"),
            signal(provider="autotask", subject_id="209", severity="high", category="tickets", summary="Single-provider issue"),
        ),
    )

    assert briefing.attention_items[0].subject_id == "208"
    assert briefing.attention_items[0].providers == ("autotask", "it-glue")
    assert briefing.attention_items[0].priority_score > briefing.attention_items[1].priority_score


def test_briefing_is_bounded() -> None:
    briefing = OperationalBriefingService().build(
        organization_id="aot",
        signals=(
            signal(provider="autotask", subject_id=str(index), severity="low", category="ticket", summary=f"Signal {index}")
            for index in range(20)
        ),
        item_limit=5,
    )

    assert len(briefing.attention_items) == 5
    assert briefing.generated_from_signal_count == 20


def test_cross_organization_signal_is_denied() -> None:
    foreign = OperationalSignal(
        source_provider="autotask",
        organization_id="other",
        subject_type="company",
        subject_id="208",
        subject_name="Other Company",
        category="ticket",
        severity="high",
        summary="Foreign organization signal",
    )

    with pytest.raises(ValueError, match="organization boundary mismatch"):
        OperationalBriefingService().build(organization_id="aot", signals=(foreign,))
