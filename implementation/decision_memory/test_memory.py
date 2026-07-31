from datetime import datetime, timedelta, timezone

from .contracts import (
    ApplicabilityRule,
    DecisionMemoryRecord,
    MatchDisposition,
    MemoryClass,
    MemoryStatus,
    NormalizedFacts,
    VerificationRecipe,
)
from .memory import DecisionMemoryMatcher, DecisionMemoryStore, stable_fingerprint


def facts(role: str = "workstation", client: str = "client-a") -> NormalizedFacts:
    return NormalizedFacts(
        organization_id="aot",
        client_id=client,
        ticket_id="T-100",
        alert_type="patch.missing",
        device_role=role,
        platform="windows",
        platform_version="11-25H2",
        attributes={
            "kb": "KB5094126",
            "patch_policy": "approved",
            "pending_reboot": "false",
        },
    )


def record_for(current_facts: NormalizedFacts) -> DecisionMemoryRecord:
    now = datetime.now(timezone.utc)
    return DecisionMemoryRecord(
        memory_id="MEM-1",
        memory_class=MemoryClass.EXACT,
        title="Verified missing patch resolution",
        status=MemoryStatus.ACTIVE,
        organization_scope="aot",
        client_scope=None,
        fingerprint=stable_fingerprint(current_facts),
        applicability=ApplicabilityRule(
            required={"alert_type": "patch.missing"},
            excluded={"device_role": ["server", "domain_controller"]},
        ),
        decision="Use approved workstation patch remediation path",
        approved_capability="remediation.patch.workstation",
        verification=VerificationRecipe(
            capability="verify.patch.installed",
            success_conditions={"installed": "true"},
        ),
        source_ticket_ids=["T-001", "T-002", "T-003"],
        created_at=now - timedelta(days=10),
        last_verified_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=30),
        owner="technology-steward",
        success_count=3,
    )


def test_verified_exact_match_can_be_reused() -> None:
    current = facts()
    result = DecisionMemoryMatcher().match(current, [record_for(current)])[0]
    assert result.disposition is MatchDisposition.REUSE
    assert result.approved_capability == "remediation.patch.workstation"


def test_server_is_excluded() -> None:
    workstation = facts()
    results = DecisionMemoryMatcher().match(facts(role="server"), [record_for(workstation)])
    assert results == []


def test_cross_organization_record_is_not_visible() -> None:
    current = facts()
    record = record_for(current)
    record.organization_scope = "different-msp"
    assert DecisionMemoryMatcher().match(current, [record]) == []


def test_unproven_record_requires_review() -> None:
    current = facts()
    record = record_for(current)
    record.success_count = 1
    result = DecisionMemoryMatcher().match(current, [record])[0]
    assert result.disposition is MatchDisposition.REVIEW
    assert result.approved_capability is None


def test_expired_record_is_ignored() -> None:
    current = facts()
    record = record_for(current)
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert DecisionMemoryMatcher().match(current, [record]) == []


def test_repeated_failures_suspend_record() -> None:
    current = facts()
    record = record_for(current)
    store = DecisionMemoryStore()
    store.add(record)
    store.record_outcome(record.memory_id, False, "T-200")
    store.record_outcome(record.memory_id, False, "T-201")
    assert store.get(record.memory_id).status is MemoryStatus.SUSPENDED
