from __future__ import annotations

import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest

from jason_runtime.dnsfilter_boundary_reconcile import (
    ReconciliationError,
    choose_company,
    fetch_dnsfilter_sites,
    load_aliases,
    normalize_name,
)


def test_normalize_name_is_case_punctuation_and_ampersand_stable():
    assert normalize_name("AVMAC LLC") == normalize_name("avmac llc")
    assert normalize_name("VisualZen, Inc.") == normalize_name("VisualZen Inc.")
    assert normalize_name("Coastal Threads Embroidery & Screen Print") == (
        "coastal threads embroidery and screen print"
    )


def test_choose_company_uses_unique_active_normalized_exact_match():
    companies = [
        {"id": 1179, "companyName": "AVMAC llc", "isActive": True},
        {"id": 99, "companyName": "AVMAC old", "isActive": False},
    ]
    company, method = choose_company("AVMAC LLC", companies, {})
    assert company is not None
    assert company["id"] == 1179
    assert method == "normalized-exact"


def test_choose_company_uses_reviewed_alias_only_when_target_is_active():
    companies = [
        {"id": 336, "companyName": "Custom Maid", "isActive": True},
        {"id": 340, "companyName": "JF Whitlow", "isActive": False},
    ]
    company, method = choose_company("Custom Maids", companies, {"custom maids": "336"})
    assert company is not None
    assert company["id"] == 336
    assert method == "alias"

    company, method = choose_company("JF Whitlow", companies, {"jf whitlow": "340"})
    assert company is None
    assert method == "alias-target-unavailable"


def test_choose_company_fails_closed_on_ambiguous_exact_match():
    companies = [
        {"id": 1, "companyName": "Example Company", "isActive": True},
        {"id": 2, "companyName": "Example Company", "isActive": True},
    ]
    company, method = choose_company("Example Company", companies, {})
    assert company is None
    assert method == "ambiguous-exact"


def test_aot_office_maps_only_to_self_company_zero():
    company, method = choose_company("AOT Office", [], {})
    assert company is not None
    assert company["id"] == 0
    assert method == "aot-self"


def test_load_aliases_normalizes_names_and_company_ids(tmp_path: Path):
    path = tmp_path / "aliases.json"
    path.write_text('{"aliases":{"FULL CIRCLE FINANCIAL":458}}', encoding="utf-8")
    assert load_aliases(path) == {"full circle financial": "458"}


def test_load_aliases_rejects_non_object_json_root(tmp_path: Path):
    path = tmp_path / "aliases.json"
    path.write_text('[{"aliases": {"FULL CIRCLE FINANCIAL": 458}}]', encoding="utf-8")
    with pytest.raises(ReconciliationError, match="aliases object"):
        load_aliases(path)


def test_fetch_dnsfilter_sites_rejects_missing_validated_master_boundary(tmp_path: Path):
    boundary_db = tmp_path / "boundary.sqlite3"
    sqlite3.connect(boundary_db).close()
    with pytest.raises(
        ReconciliationError,
        match="validated AOT DNSFilter master boundary is required",
    ):
        fetch_dnsfilter_sites(
            role_id_path=tmp_path / "role_id",
            secret_id_path=tmp_path / "secret_id",
            boundary_db=boundary_db,
        )
