from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.autotask_vendor_entity_catalog import parse_documented_entity_names


ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "docs/operations/Autotask-REST-Entity-Index-20261027.json"
META = ROOT / "docs/operations/Autotask-Live-Schema-Observations-20261027.json"


def test_public_index_snapshot_is_a_documentation_candidate_not_a_grant():
    doc = json.loads(INDEX.read_text())
    assert doc["entity_count"] >= 200
    assert len(doc["entity_names"]) == doc["entity_count"]
    assert len(set(doc["entity_names"])) == doc["entity_count"]
    assert "NOT proof" in doc["note"]
    assert {"Tasks", "Tickets", "TimeEntries", "Projects"}.issubset(doc["entity_names"])


def test_index_parser_roundtrip_uses_public_documented_entity_row_names_only():
    names = json.loads(INDEX.read_text())["entity_names"]
    html = "<table><tr><th>Entity</th><th>Description</th><th>Webhooks</th></tr>" + "".join(
        "<tr><td>" + name + "</td><td>Vendor name only</td><td></td></tr>"
        for name in names
    ) + "<tr><td>../Secrets</td><td>invalid</td><td></td></tr></table>"
    assert parse_documented_entity_names(html) == names


def test_parser_does_not_succeed_on_truncated_page():
    with pytest.raises(ValueError, match="incomplete"):
        parse_documented_entity_names("<tr><td>Tickets</td><td>desc</td><td></td></tr>")


def test_observations_are_not_confused_with_public_index_or_permission_grants():
    doc = json.loads(INDEX.read_text())
    evidence = json.loads(META.read_text())
    assert len(evidence["entities"]) < doc["entity_count"]
    assert all(v["canQuery"] is True for v in evidence["entities"].values())
    assert evidence["entities"]["Invoices"]["userAccessForQuery"] == "None"
    assert evidence["entities"]["BillingItems"]["userAccessForQuery"] == "None"
    assert evidence["entities"]["Phases"]["userAccessForQuery"] == "All"
    assert evidence["entities"]["TaskNotes"]["userAccessForQuery"] == "All"


def test_generated_csv_matches_source_snapshots_and_never_claims_full_access():
    import csv
    csv_path = ROOT / "docs/operations/Autotask-Read-Coverage-Matrix-20261027.csv"
    with csv_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == json.loads(INDEX.read_text())["entity_count"]
    by_name = {row["entity"]: row for row in rows}
    assert by_name["Invoices"]["assessment"] == "provider_user_query_denied"
    assert by_name["Tickets"]["assessment"] == "named_route_active_requires_live_read_proof"
    assert by_name["Phases"]["assessment"] == "governed_query_route_gap"
    assert by_name["Phases"]["live_record_read_verified"] == "False"
    assert by_name["Phases"]["generic_capabilities_active"] == "False"
