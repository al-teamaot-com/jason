from datetime import datetime, timedelta, timezone

import pytest

from implementation.triage_intelligence.contracts import (
    EvidenceItem,
    EvidenceKind,
    NormalizedSymptoms,
    RankedFinding,
    TicketContext,
    TriageOutcome,
)
from implementation.triage_intelligence.engine import (
    ScopeViolationError,
    TriageIntelligenceEngine,
)


class Normalizer:
    def normalize(self, ticket):
        return NormalizedSymptoms(
            summary="Taskbar icon is missing",
            symptoms=("icon missing",),
            products=("Windows 11",),
        )


class Provider:
    provider_name = "platform"

    def __init__(self, items):
        self.items = items

    def search(self, *, ticket, symptoms):
        return self.items


class Ranker:
    def rank(self, *, ticket, symptoms, evidence):
        if not evidence:
            return ()
        return (
            RankedFinding(
                outcome=TriageOutcome.EXPECTED_BEHAVIOR,
                confidence=0.91,
                explanation="The symptom matches a documented platform change.",
                evidence_ids=(evidence[0].evidence_id,),
                recommended_action="Verify the installed build and explain the change.",
            ),
        )


def ticket():
    return TicketContext(
        ticket_id="T-1",
        title="Icon missing",
        description="My taskbar icon disappeared.",
        organization_id="aot",
        client_id="client-1",
    )


def evidence(**overrides):
    values = dict(
        evidence_id="E-1",
        kind=EvidenceKind.PLATFORM_CHANGE,
        source_name="Microsoft",
        source_reference="official-doc-reference",
        title="Taskbar behavior changed",
        summary="The icon is no longer shown in this build.",
        observed_at=datetime.now(timezone.utc),
        organization_id=None,
        client_id=None,
        confidence=0.95,
        authoritative=True,
    )
    values.update(overrides)
    return EvidenceItem(**values)


def test_returns_evidence_backed_expected_behavior_finding():
    engine = TriageIntelligenceEngine(
        normalizer=Normalizer(), providers=(Provider((evidence(),)),), ranker=Ranker()
    )

    result = engine.assess(ticket())

    assert result.findings[0].outcome is TriageOutcome.EXPECTED_BEHAVIOR
    assert result.findings[0].evidence_ids == ("E-1",)
    assert result.requires_human_review is True


def test_blocks_cross_client_evidence():
    engine = TriageIntelligenceEngine(
        normalizer=Normalizer(),
        providers=(Provider((evidence(client_id="client-2"),)),),
        ranker=Ranker(),
    )

    with pytest.raises(ScopeViolationError):
        engine.assess(ticket())


def test_discards_expired_evidence_and_reports_insufficient_evidence():
    expired = evidence(valid_until=datetime.now(timezone.utc) - timedelta(days=1))
    engine = TriageIntelligenceEngine(
        normalizer=Normalizer(), providers=(Provider((expired,)),), ranker=Ranker()
    )

    result = engine.assess(ticket())

    assert result.evidence == ()
    assert result.findings == ()
    assert result.insufficient_evidence
