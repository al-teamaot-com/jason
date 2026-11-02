"""Source-only validation for the owner-approved AOT client question library."""
from __future__ import annotations

import json
from pathlib import Path

CATALOG = (
    Path(__file__).resolve().parents[3]
    / "config/client_communications/information_requests_round1.json"
)
LIVE = (
    Path(__file__).resolve().parents[3]
    / "config/client_communications/approved.json"
)


def _load():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def test_round1_contains_all_120_exact_stable_ids():
    data = _load()
    assert data["schema_version"] == 1
    assert len(data["questions"]) == 120
    assert [q["question_id"] for q in data["questions"]] == [
        f"JQ-{i:03d}" for i in range(1, 121)
    ]
    assert len({q["template_id"] for q in data["questions"]}) == 120
    assert len({q["category"] for q in data["questions"]}) == 15


def test_library_is_content_only_and_never_enables_send():
    data = _load()
    assert data["production_activation"] is False
    assert data["send_authority"] == "none-from-catalog"
    for q in data["questions"]:
        assert q["content_approved"] is True
        assert q["autonomous_send_enabled"] is False
        assert q["review_class"] in {"routine", "context_controlled", "human_review"}
        assert q["title"].strip()
        assert q["body"].strip()


def test_standard_footer_is_exact_and_ticket_placeholder_is_bounded():
    footer = _load()["footer"]
    assert footer["template_id"] == "client-support-footer-v1"
    assert footer["placeholders"] == ["ticket_number"]
    assert "support@teamaot.com" in footer["body"]
    assert "757-466-8862" in footer["body"]
    assert footer["body"].count("{{ticket_number}}") == 1


def test_not_enrolled_into_existing_live_registry():
    data = _load()
    live = json.loads(LIVE.read_text(encoding="utf-8"))
    live_ids = {entry["template_id"] for entry in live["templates"]}
    assert data["footer"]["template_id"] not in live_ids
    assert not live_ids.intersection(
        q["template_id"] for q in data["questions"]
    )
