"""Source-only AOT-MSA initial Service creation acceptance; no provider I/O."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "implementation"))

from connectors.autotask.procurement_mutation_connector import (  # noqa: E402
    AutotaskProcurementMutationConnector,
)

REQUEST = ROOT / "docs/catalog/AOT_MSA_FIRST_CATALOG_WRITE_ACCEPTANCE_20261117.json"


def _payload():
    return json.loads(REQUEST.read_text(encoding="utf-8"))


def test_exact_inactive_zero_charge_request_is_accepted_by_native_connector():
    plan = _payload()
    assert plan["authorized_to_execute"] is False
    assert plan["exact_action_approval_recorded"] is False
    assert plan["exact_grant_verified"] is False
    assert plan["production_catalog_release_verified"] is False
    assert plan["human_approval_required"] is True
    assert plan["execution_identity"].startswith("Jason dedicated")
    request = plan["exact_request"]
    assert request["capability"] == "service.service.create"
    raw = request["arguments"]["payload"]
    assert raw["name"] == "AOT-MSA – Catalog Write Acceptance"
    assert raw["sku"] == "AOT-MSA-CATALOG-TEST-001"
    assert raw["isActive"] is False
    assert raw["periodType"] == 2
    assert raw["billingCodeID"] == 29682901
    assert type(raw["unitPrice"]) in (int, float)
    assert raw["unitPrice"] == raw["unitCost"] == 0
    assert "ImpersonationResourceId" not in json.dumps(request)
    assert "http" not in json.dumps(request)
    assert "contractID" not in json.dumps(raw)

    normalized = AutotaskProcurementMutationConnector._validated_payload(
        "autotask.service.create", raw
    )
    assert normalized == raw


def test_exact_request_requires_distinct_release_grant_and_owner_approval():
    plan = _payload()
    prerequisites = "\n".join(plan["preconditions"])
    checks = "\n".join(plan["expected_postconditions"])
    assert "scoped native root installer" in prerequisites
    assert "grant" in prerequisites and "Owner" in prerequisites
    assert "No ImpersonationResourceId" in checks
    assert "Same ID" not in checks
    assert "No contract" in checks
    assert "no second creation attempt" in checks
    assert plan["failure_policy"].startswith("Fail closed.")


def test_native_rejects_unapproved_service_field_injection():
    original = _payload()["exact_request"]["arguments"]["payload"]
    for unexpected in ("companyID", "contractID", "ImpersonationResourceId"):
        with pytest.raises(PermissionError, match="AUTOTASK_PROCUREMENT_FIELD_NOT_ALLOWED"):
            AutotaskProcurementMutationConnector._validated_payload(
                "autotask.service.create", {**original, unexpected: 1}
            )
