#!/usr/bin/env python3
"""Emit an evidence-only Autotask entity coverage matrix; no provider access."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from connectors.autotask.read_coverage_inventory import assess_coverage

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs" / "operations"
INDEX = DIRECTORY / "Autotask-REST-Entity-Index-20261027.json"
EVIDENCE = DIRECTORY / "Autotask-Live-Schema-Observations-20261027.json"
OUTPUT = DIRECTORY / "Autotask-Read-Coverage-Matrix-20261027.csv"
SUMMARY = DIRECTORY / "Autotask-Read-Coverage-Matrix-20261027.md"
FIELDS = (
    "entity", "vendor_documented", "source_connector_entity_registered",
    "provider_metadata_observed", "provider_can_query", "provider_user_query_access",
    "field_metadata_observed", "field_count", "specialized_handling",
    "generic_source_registered", "generic_capabilities_active",
    "named_route_source_registered", "named_route_capabilities_active", "assessment",
    "live_record_read_verified", "pagination_verified", "disclosure_negative_tests_verified",
)


def generate() -> dict:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert index["entity_count"] == len(index["entity_names"])
    assert evidence["entity_count"] == len(evidence["entities"])
    report = assess_coverage(
        provider_entity_information=evidence["entities"],
        vendor_documented_entities=index["entity_names"],
        active_capabilities=frozenset(
            json.loads((DIRECTORY / "Autotask-Live-Read-Capabilities-20261027.json").read_text())["read_capabilities"]
        ),  # Explicit 2026-10-27 governed registry snapshot (v10).
    )
    with OUTPUT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["rows"])
    rows = report["rows"]
    observed = [r for r in rows if r["provider_metadata_observed"]]
    allowed = [r for r in observed if r["provider_user_query_access"] == "All"]
    denied = [r for r in observed if r["provider_user_query_access"] == "None"]
    coverage = len(observed) / len(rows)
    named_active = sum(bool(r["named_route_capabilities_active"]) for r in rows)
    text = (
        "# Autotask Read Coverage Audit — 2026-10-27\n\n"
        "**Status: documentation / provider-metadata inventory only; no new production reads activated.**\n\n"
        "| Measurement | Evidence-backed value |\n|---|---:|\n"
        f"| Public documentation candidate entity names | {index['entity_count']} |\n"
        f"| Distinct union of public and source-known names | {len(rows)} |\n"
        f"| Existing Jason connector source-known names | {report['source_registered_entity_count']} |\n"
        f"| Live governed schema checks succeeded | {len(observed)} |\n"
        f"| API integration userAccessForQuery=All | {len(allowed)} |\n"
        f"| API integration userAccessForQuery=None | {len(denied)} |\n"
        f"| Live entity-record queries validated through new generic route | 0 |\n"
        f"| Named entity families with at least one live read route | {named_active} |\n"
        f"| Vendor candidate metadata verified | {coverage:.1%} |\n\n"
        "## Important distinctions\n\n"
        "The published index contains candidates, not an authenticated API account's permissions. "
        "The presence of `canQuery=true` alone is insufficient; user-specific "
        "`userAccessForQuery=None` remains a provider denial. The metadata evidence "
        "is not a successful record query, field-completeness test, child traversal, "
        "pagination test, or proof that a user may receive a result. "
        "An API read and requester disclosure remain separate decisions.\n\n"
        "Known provider-account metadata restrictions: "
        + ", ".join(r["entity"] for r in denied) + ".\n\n"
        "## Next engineering gates\n\n"
        "1. Continue live governed entityInformation/fields metadata discovery for the remaining names; "
        "record unsupported names and query-only endpoints separately.\n"
        "2. Review field visibility, sensitive attachments and labor, child relations, "
        "and preserve named audited provider routes without enabling generic raw HTTP.\n"
        "3. Add the missing versioned bounded read-only routes, full pagination and exact ID proof, "
        "plus negative requester-disclosure and mutation non-escalation tests.\n"
        "4. Merge reviewed source under protected CI. Production promotion stays frozen "
        "until a separate exact-SHA owner exception, verified baseline and native rollback.\n\n"
        "Sources: [Autotask REST entity index](" + index["source_url"] + "), "
        "governed AOT `service.entity.describe` metadata snapshot in "
        "`Autotask-Live-Schema-Observations-20261027.json`. "
        "Machine-readable detailed evidence classification is in the sibling CSV.\n"
    )
    SUMMARY.write_text(text, encoding="utf-8")
    return {
        "documented_candidates": index["entity_count"],
        "union": len(rows),
        "metadata_verified": len(observed),
        "api_user_all": len(allowed),
        "api_user_none": len(denied),
        "source_registered": report["source_registered_entity_count"],
        "named_entity_families_active": named_active,
    }


if __name__ == "__main__":
    print(json.dumps(generate(), sort_keys=True))
