"""Project-specific approval-policy exception; production remains gated."""
from pathlib import Path
from tools import pmv4_stage_a0_one_owner_review as review


def test_approved_one_release_exception_is_limited_and_not_an_owner_signature():
    path = Path(__file__).parents[1] / "docs/operations/PMv4-Stage-A0-One-Release-Approval-Decision-20261115.md"
    doc = path.read_text()
    assert "2026-11-15" in doc
    assert "issue #2481" in doc
    assert "three specified Stage A0 operations" in doc
    assert "NOT" in doc and "production release not authorized" in doc
    for _, _, scope, artifact in review.REVIEWED_ACTIONS:
        assert scope in doc
        assert artifact in doc
    exact = review.exact_contract()
    assert exact["owner_decisions"] == 1
    assert exact["production_apply_supported"] is False
    assert len(exact["ordered_actions"]) == 3
    assert exact["source_sha"] == review.SOURCE
    assert exact["lkg_sha"] == review.LKG
