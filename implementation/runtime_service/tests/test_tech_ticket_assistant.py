from jason_runtime.gpt_insights import InsightEvidence
from jason_runtime.tech_ticket_assistant import build_tech_ticket_advisory


def test_advisory_is_bounded_read_only_and_high_signal():
    evidence = InsightEvidence(
        category="network",
        ticket_number="T1",
        ticket_title="Wi-Fi keeps dropping",
        device_name="PC-1",
        device_online=True,
        operating_system="Windows 11 Pro",
        connection_summary="Wi-Fi: Wi-Fi (AlphaPsych)",
        related_ticket_count=0,
        site_correlation="No site-wide conclusion is established.",
    )
    result = build_tech_ticket_advisory(evidence)
    assert result.confidence == "moderate"
    assert 1 <= len(result.next_steps) <= 3
    assert all(step.kind == "diagnostic" for step in result.next_steps)
    assert result.approval_required
    assert "root cause" in result.assessment.casefold()


def test_advisory_does_not_repeat_attempted_step():
    evidence = InsightEvidence(
        category="performance",
        ticket_number="T2",
        ticket_title="PC is slow",
        device_name="PC-2",
        device_online=True,
    )
    attempted = [
        "Check uptime, top CPU/memory consumers, free memory, and recent System/Application errors."
    ]
    result = build_tech_ticket_advisory(evidence, attempted_steps=attempted)
    assert all("uptime" not in step.action.casefold() for step in result.next_steps)


def test_unknown_ticket_does_not_invent_root_cause():
    evidence = InsightEvidence(
        category="unknown",
        ticket_number="T3",
        ticket_title="Need help",
        unresolved_reason="No configuration item is associated.",
    )
    result = build_tech_ticket_advisory(evidence)
    assert result.confidence == "low"
    assert "does not support" in result.assessment
    assert len(result.next_steps) == 1


def test_prior_resolution_is_evidence_not_instruction():
    evidence = InsightEvidence(
        category="application",
        ticket_number="T4",
        ticket_title="Application error",
        device_name="PC-4",
        device_online=True,
    )
    result = build_tech_ticket_advisory(
        evidence,
        prior_resolution_hints=("Reinstalling version 7.2 resolved a similar case",),
    )
    assert result.remediation_options
    assert "Re-verify applicability" in result.remediation_options[0]
