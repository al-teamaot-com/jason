from jason_runtime.technical_notes import (
    SECTION_ORDER,
    TechnicalNote,
    canonical_title,
    legacy_technical_note,
    render_technical_note,
)


def test_render_technical_note_uses_fixed_section_order():
    note = TechnicalNote(
        kind="technical_review",
        status="Diagnostic Complete",
        issue="DNS Agent stopped",
        scope=["Ticket=T1", "Device=PC1"],
        findings=["Service is stopped."],
        evidence=["ServiceState=Stopped"],
        actions_taken=["No remediation performed."],
        verification=["Endpoint identity verified."],
        next_action="Resume when endpoint is online.",
        jason_state=["Playbook=dns_agent_diagnostic", "Phase=waiting_device_access"],
    )
    body = render_technical_note(note)
    positions = [body.index(f"{section}:") for section in SECTION_ORDER]
    assert positions == sorted(positions)
    assert body.count("NEXT ACTION:") == 1
    assert body.count("JASON STATE:") == 1


def test_canonical_titles_are_bounded_and_predictable():
    assert canonical_title("technical_review") == "Jason - Technical Review"
    assert canonical_title("waiting") == "Jason - Waiting State"
    assert canonical_title("human_review") == "Jason - Human Review Required"
    assert canonical_title("resolution") == "Jason - Resolution"


def test_legacy_adapter_preserves_detail_and_extracts_next_action():
    note = legacy_technical_note(
        title="Jason - VulScan - Waiting Patch Approval",
        body=(
            "Device=PC1; KB5126052=NOT_APPROVED. "
            "No forced installation or reboot was attempted. "
            "NEXT STEP: Jason will recheck the exact KB approval state daily."
        ),
        issue="Vulnerability Detected",
        scope=["Ticket=T2", "Device=PC1"],
        playbook="vulscan_missing_patch",
        phase="waiting_patch_approval",
        reason="patch approval pending",
    )
    assert note.kind == "waiting"
    assert note.status == "Waiting"
    assert note.next_action == "Jason will recheck the exact KB approval state daily."
    body = render_technical_note(note)
    assert "KB5126052=NOT_APPROVED" in body
    assert "No forced installation or reboot was attempted." in body
    assert "Playbook=vulscan_missing_patch" in body
    assert "Phase=waiting_patch_approval" in body


def test_lifecycle_phase_overrides_legacy_title_for_handoff():
    note = legacy_technical_note(
        title="Jason - BackupIQ - Managed Endpoint Missing",
        body="Technician review is required to determine managed coverage.",
        issue="Backup unavailable",
        scope=["Ticket=T3", "Device=SOS-50767"],
        playbook="backupiq_endpoint_backup",
        phase="escalated",
        reason="technician review required",
    )
    assert note.kind == "human_review"
    assert note.status == "Human Review Required"
    assert canonical_title(note.kind) == "Jason - Human Review Required"
    assert note.next_action == "Technician review is required before Jason can continue safely."