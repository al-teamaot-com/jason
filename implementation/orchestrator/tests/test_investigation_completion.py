from __future__ import annotations

import pytest

from orchestrator.conversation_answer import ConversationLimitation, ConversationSupport
from orchestrator.conversation_kernel import InformationNeed, InformationTarget
from orchestrator.investigation_completion import (
    InvestigationIncompleteError,
    NeedCompletionRecord,
    require_investigation_completion,
)


def need(value: str) -> InformationNeed:
    return InformationNeed(
        target=InformationTarget(kind="generic_resource", source="literal", reference="RESOURCE"),
        need=value,
        authority="observe",
    )


def support(value: str) -> ConversationSupport:
    return ConversationSupport(
        support_id=f"support-{value}",
        information_need=value,
        target_reference="RESOURCE",
        value="verified",
        evidence_reference="execution:/verified",
    )


def record(value: str, disposition: str, terminal_reason=None) -> NeedCompletionRecord:
    return NeedCompletionRecord(
        information_need=value,
        target_reference="RESOURCE",
        disposition=disposition,
        attempted_reads=("governed.primary.read",),
        terminal_reason=terminal_reason,
    )


def test_all_needs_with_governed_evidence_pass():
    require_investigation_completion(
        needs=(need("backup status"), need("current configuration")),
        records=(record("backup status", "supported"), record("current configuration", "supported")),
        supports=(support("backup status"), support("current configuration")),
        limitations=(),
    )


def test_partial_support_without_second_need_is_rejected():
    with pytest.raises(InvestigationIncompleteError):
        require_investigation_completion(
            needs=(need("current state"), need("historical trend")),
            records=(record("current state", "supported"),),
            supports=(support("current state"),),
            limitations=(),
        )


def test_limitation_requires_explicit_exhaustion_reason():
    with pytest.raises(ValueError):
        record("requested evidence", "limited")


def test_authorized_reads_exhausted_are_not_misrepresented_as_success():
    require_investigation_completion(
        needs=(need("historical trend"),),
        records=(record("historical trend", "limited", "no_further_authorized_read"),),
        supports=(),
        limitations=(ConversationLimitation(
            information_need="historical trend",
            reason="no available governed resource establishes the requested history",
        ),),
    )


def test_unsupported_evidence_cannot_be_called_supported():
    with pytest.raises(InvestigationIncompleteError):
        require_investigation_completion(
            needs=(need("scheduled recurrence"),),
            records=(record("scheduled recurrence", "supported"),),
            supports=(support("script exists"),),
            limitations=(),
        )


def test_disposition_must_match_the_human_need_not_a_nearby_fact():
    with pytest.raises(InvestigationIncompleteError):
        require_investigation_completion(
            needs=(need("actual recurrence"),),
            records=(record("manual execution", "supported"),),
            supports=(support("manual execution"),),
            limitations=(),
        )


def test_limits_must_not_be_silently_dropped():
    with pytest.raises(InvestigationIncompleteError):
        require_investigation_completion(
            needs=(need("history"),),
            records=(record("history", "limited", "read_budget_exhausted"),),
            supports=(),
            limitations=(),
        )
