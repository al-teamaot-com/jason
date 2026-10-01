from datetime import datetime, timezone

from jason_runtime.gpt_insights import (
    InsightEvidence,
    classify_ticket,
    connection_summary,
    material_fingerprint,
    note_title,
    render_insight,
)


def test_classifies_network_and_does_not_need_human_wifi_question():
    assert classify_ticket("Internet drops", "My PC disconnects randomly") == "network"
    summary = connection_summary([
        {"Name": "Wi-Fi", "PhysicalMediaType": "Native 802.11", "Profile": "OfficeWiFi"}
    ])
    assert summary == "Wi-Fi: Wi-Fi (OfficeWiFi)"


def test_unknown_ticket_states_uncertainty_instead_of_inventing():
    ev = InsightEvidence(category="unknown", ticket_number="T1", ticket_title="Please call me")
    body = render_insight(ev)
    assert "could not confidently classify" in body
    assert "Do not ask for discoverable facts" in body


def test_material_fingerprint_changes_when_new_device_evidence_arrives():
    a = InsightEvidence(category="network", ticket_number="T1", ticket_title="x", device_online=True)
    b = InsightEvidence(category="network", ticket_number="T1", ticket_title="x", device_online=False)
    assert material_fingerprint(a) != material_fingerprint(b)


def test_update_title_is_timestamped():
    title = note_title(update=True, now=datetime(2026, 10, 1, 13, 5, tzinfo=timezone.utc))
    assert title == "GPT Insights - Update 2026-10-01 13:05 UTC"
