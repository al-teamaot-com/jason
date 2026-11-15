"""Regression for the Nov 15 production LKG-vs-PMv4-candidate root verifier defect."""
from __future__ import annotations

from pathlib import Path
import json
import pytest

from tools import owner_v2_issuer_aware_root_updater as updater
from tools import owner_full_integrity_v2_root_repair as health


@pytest.fixture
def receipt():
    action = "pmv4-stage-a0-same-image-owner-issuer-v1"
    image = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
    current_id = "0fdb6e0656bbc2733bae6104c484387fc06cfc5e71da808e06728c4941f1b8c0"
    attempt = {
        "action": action,
        "source": updater.LKG,  # Actual Nov 14 root-issued production source.
        "mcp_image": image,
        "freeze_sha256": updater.FREEZE_SHA,
        "status": "exact_one_use_claimed_before_mutation",
    }
    result = {"action": action, "result": "verified", "new_mcp_id": current_id}
    return attempt, result, image, current_id


def test_stage_a0_historical_issuer_uses_production_lkg_not_stage_candidate(receipt):
    attempt, outcome, image, live_id = receipt
    assert updater.LKG == health.ISSUER_SOURCE == health.LKG
    assert updater.LKG != updater.MERGE
    updater.verify_existing_issuer_receipt(
        attempt, outcome, current_mcp_id=live_id, expected_mcp_image=image,
    )
    source_policy = Path(
        "/srv/jason/archive/pmv4-stage-a0-PREP-ONLY-issuer-activation-policy-7b42ce983896711525de4c7955bf9fc43ac003d0.json"
    )
    if source_policy.exists():
        assert json.loads(source_policy.read_bytes())["source_sha"] == updater.LKG


@pytest.mark.parametrize("field,value,code", [
    ("source", updater.MERGE, "HISTORICAL_LKG_MISMATCH"),
    ("source", "0" * 40, "HISTORICAL_LKG_MISMATCH"),
    ("status", "not_approved", "AUDIT_ATTEMPT_NOT_CLAIMED"),
    ("mcp_image", "sha256:" + "0" * 64, "HISTORICAL_IMAGE_MISMATCH"),
    ("freeze_sha256", "0" * 64, "HISTORICAL_FREEZE_MISMATCH"),
])
def test_tampered_historical_claim_denied(receipt, field, value, code):
    attempt, outcome, image, live_id = receipt
    attempt[field] = value
    with pytest.raises(updater.RootUpdateDenied, match=code):
        updater.verify_existing_issuer_receipt(
            attempt, outcome, current_mcp_id=live_id, expected_mcp_image=image,
        )


@pytest.mark.parametrize("field,value,code", [
    ("result", "failed", "AUDIT_RESULT_NOT_VERIFIED"),
    ("new_mcp_id", "another-container-id", "AUDIT_LIVE_MCP_ID_MISMATCH"),
    ("action", "unknown", "AUDIT_ACTION_MISMATCH"),
])
def test_tampered_issuer_result_denied(receipt, field, value, code):
    attempt, outcome, image, live_id = receipt
    outcome[field] = value
    with pytest.raises(updater.RootUpdateDenied, match=code):
        updater.verify_existing_issuer_receipt(
            attempt, outcome, current_mcp_id=live_id, expected_mcp_image=image,
        )


def test_previous_failed_scope_is_not_reusable_as_fixed_scope():
    assert updater.ACTION.endswith("-v2-20261115")
    assert "issuer-attested-v2" in str(updater.OWNER_DECISION)
    assert "issuer-attested-v2" in str(updater.AUDIT_ATTEMPT)
    assert updater.SCOPE != "cf866a84f38fc0b45decb7bf0a87ac34232bf124be3b1796e6a243cb86bfb196"
    assert updater.PACKAGE_SHA != "b221e48383cef5cfd69fdd24b38c08ceacf8459a1b7c0b62dab6036fd721006c"
