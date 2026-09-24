from __future__ import annotations

from pathlib import Path

import pytest

from tools.backup_net_boundary import (
    BoundaryDiscoveryError,
    _exact_asset,
    _exact_customer,
    _persist_boundary,
    _prove_empty_asset_inventory,
)

CUSTOMER_ID = "d28a556c-d8de-48f9-8a64-90fdf03ec4d0"


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, path, params):
        self.calls.append((path, dict(params)))
        return self.responses.pop(0)


def test_exact_customer_requires_one_exact_name():
    client = FakeClient([
        {"items": [{"id": CUSTOMER_ID, "name": "Deborah Gittens Virtuol Designs LLC"}]}
    ])
    customer_id, name = _exact_customer(
        client,
        "Deborah Gittens Virtuol Designs LLC",
    )
    assert customer_id == CUSTOMER_ID
    assert name == "Deborah Gittens Virtuol Designs LLC"
    assert client.calls[0][0] == "/v1/customers"


def test_exact_customer_rejects_ambiguous_exact_matches():
    client = FakeClient([
        {
            "items": [
                {"id": CUSTOMER_ID, "name": "Client A"},
                {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "Client A"},
            ]
        }
    ])
    with pytest.raises(BoundaryDiscoveryError, match="exactly one"):
        _exact_customer(client, "Client A")


def test_exact_asset_must_prove_same_customer():
    client = FakeClient([
        {
            "items": [
                {
                    "id": "DGV-50859",
                    "name": "DGV-50859",
                    "customerId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                }
            ]
        }
    ])
    with pytest.raises(BoundaryDiscoveryError, match="does not match"):
        _exact_asset(client, customer_id=CUSTOMER_ID, asset_name="DGV-50859")


def test_empty_asset_inventory_proves_zero_asset_customer():
    client = FakeClient([{"items": []}])
    proof = _prove_empty_asset_inventory(client, customer_id=CUSTOMER_ID)
    assert proof == {"inventory_empty": True}
    path, params = client.calls[0]
    assert path == "/api/epb/v1/assets"
    assert params["customer_id"] == CUSTOMER_ID
    assert params["page_number"] == 1
    assert params["page_size"] == 1


def test_empty_asset_inventory_rejects_customer_with_assets():
    client = FakeClient([{"items": [{"id": "asset-1"}]}])
    with pytest.raises(BoundaryDiscoveryError, match="exact asset proof"):
        _prove_empty_asset_inventory(client, customer_id=CUSTOMER_ID)


def test_persist_boundary_accepts_autotask_company_zero(tmp_path: Path):
    db = tmp_path / "boundaries-zero.sqlite3"
    boundary_id, created = _persist_boundary(
        db_path=db,
        company_id="0",
        customer_id=CUSTOMER_ID,
        primary_domain="teamaot.com",
    )
    assert boundary_id
    assert created is True


def test_persist_boundary_is_idempotent_for_same_mapping(tmp_path: Path):
    db = tmp_path / "boundaries.sqlite3"
    boundary_id, created = _persist_boundary(
        db_path=db,
        company_id="1627",
        customer_id=CUSTOMER_ID,
        primary_domain="virtuoldesigns.com",
    )
    assert created is True
    same_id, created_again = _persist_boundary(
        db_path=db,
        company_id="1627",
        customer_id=CUSTOMER_ID,
        primary_domain="virtuoldesigns.com",
    )
    assert same_id == boundary_id
    assert created_again is False
