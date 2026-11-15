"""Immutable three-step one-Owner Stage A0 review; no production mutation."""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import pytest

from implementation.mcp_service.src.jason_mcp.pmv4_bounded_owner_bridge import (
    authorize_one_bounded_objective_from_mcp,
)
from kernel.signed_owner_release import OWNER_PRINCIPAL
from orchestrator.pmv4_objective_scope import (
    issue_proved_objective_step, verify_proved_objective_step,
)
from tools import pmv4_stage_a0_one_owner_review as review
from test_pmv4_owner_objective_end_to_end import (
    AT, APPROVAL_ID, enrolled, observed,
)


def test_immutable_exact_source_review_and_full_three_action_plan():
    result = review.verify_review(repo=Path(__file__).resolve().parents[1])
    assert result["status"] == "verified_source_only_no_root_authority"
    assert result["steps"] == 3
    assert result["production_approval_issued"] is False
    assert result["root_mutations"] == 0
    objective = review.build_reviewed_plan(expires_at=AT + timedelta(minutes=30))
    assert len(objective.actions) == 3
    assert objective.rollback_sha == review.LKG
    assert objective.candidate_sha == review.SOURCE
    assert objective.freeze_sha256 == review.FREEZE
    assert objective.hold_sha256 == review.HOLD
    assert {a.capability for a in objective.actions} == {item[0]
                                                         for item in review.REVIEWED_ACTIONS}
    assert all(a.rollback_sha == review.ZERO for a in objective.actions)
    assert objective.review_material()["actions"][0]["scope_sha256"] == review.REVIEWED_ACTIONS[0][2]
    assert objective.review_material()["actions"][1]["artifact_sha256"] == review.MISSING_SHA
    assert objective.review_material()["actions"][2]["artifact_sha256"] == review.NATIVE_MANIFEST


def test_one_owner_authenticates_combined_full_plan_and_three_independent_steps(enrolled):
    obj = review.build_reviewed_plan(expires_at=AT + timedelta(minutes=30))
    enrolled["objective"] = obj
    decisions = []
    parent = authorize_one_bounded_objective_from_mcp(
        bearer_token=enrolled["token"],
        verified_owner_principal=OWNER_PRINCIPAL,
        verified_organization="aot",
        verify_entra_bearer=enrolled["verifier"],
        exact_owner_consent=lambda shown: decisions.append(shown) or True,
        protected_main_check=lambda source: source == review.SOURCE,
        objective=obj, ledger=enrolled["ledger"],
        signing_key=enrolled["owner_key"], approval_id=APPROVAL_ID,
        affirmative_decision="approve_exact_one_pmv4_objective",
        at=AT,
    )["signed_parent"]
    assert len(decisions) == 1
    assert decisions[0]["full_reviewed_objective"] == obj.review_material()
    for step in range(3):
        facts = observed(obj, step)
        signed = issue_proved_objective_step(
            objective=obj, ledger=enrolled["ledger"],
            signed_parent=parent, signing_key=enrolled["owner_key"],
            pinned_public_key=enrolled["owner_key"].public_key(),
            action_index=step, observed=facts,
            verified_prior_steps=frozenset(range(step)), at=AT,
        )
        out = verify_proved_objective_step(
            objective=obj, ledger=enrolled["ledger"],
            signed_parent=parent, signed_step=signed,
            pinned_public_key=enrolled["owner_key"].public_key(),
            action_index=step, observed=facts,
            verified_prior_steps=frozenset(range(step)), at=AT,
        )
        assert out["rollback_sha"] == review.ZERO
        assert out["scope_sha256"] == obj.actions[step].scope_sha256
    assert len(decisions) == 1
    assert enrolled["ledger"].authenticated_owner_objective_receipt(
        plan_id=obj.plan_id, approval_id=APPROVAL_ID) == parent


def test_archived_source_evidence_agrees_with_reviewed_exact_live_packet_if_present():
    if not review.BOOTSTRAP.exists() or not review.ONEFILE.exists():
        pytest.skip("archive receipts live only on the authorized Jason device")
    review.read_archive_proof()


@pytest.mark.parametrize("fault", ["altered_step", "new_action", "enabled_apply",
                                    "unfrozen_controls", "new_file", "wrong_rollback",
                                    "source_main"])
def test_changed_exact_review_contract_denied_before_owner_consent(fault, monkeypatch,
                                                                    tmp_path):
    source = json.loads(review.CONTRACT.read_bytes())
    if fault == "altered_step":
        source["ordered_actions"][1]["scope_sha256"] = "e" * 64
    elif fault == "new_action":
        source["ordered_actions"].append(source["ordered_actions"][0])
    elif fault == "enabled_apply":
        source["production_apply_supported"] = True
    elif fault == "unfrozen_controls":
        source["freeze_sha256"] = "f" * 64
    elif fault == "new_file":
        source["one_missing_root_file"] = "/etc/passwd"
    elif fault == "wrong_rollback":
        source["ordered_actions"][2]["rollback_sha"] = review.LKG
    elif fault == "source_main":
        source["source_sha"] = "f" * 40
    foreign = tmp_path / "modified-plan.json"
    foreign.write_text(json.dumps(source))
    monkeypatch.setattr(review, "CONTRACT", foreign)
    with pytest.raises(review.PMv4StageA0ReviewDenied,
                       match="OWNER_PLAN_REVIEW_SOURCE_CHANGED"):
        review.exact_contract()


def test_invalid_source_or_expiry_denied():
    with pytest.raises(review.PMv4StageA0ReviewDenied, match="EXACT_EXPIRY"):
        review.build_reviewed_plan(expires_at=AT.replace(tzinfo=None))
    with pytest.raises(review.PMv4StageA0ReviewDenied, match="SOURCE_REV_CHANGED"):
        review.read_source_evidence(blob_revision=review.LKG)


def test_contract_never_grants_native_root_authority():
    obj = review.build_reviewed_plan(expires_at=AT + timedelta(minutes=30))
    contract = review.exact_contract()
    assert contract["owner_decisions"] == 1
    assert contract["production_apply_supported"] is False
    assert contract["status"] == "source_only_not_authorized"
    assert contract["require_independent_root_acceptance"] is True
    assert contract["must_not_change"] == [
        "ticket_runtime", "mcp_image", "production_lkg_pointer",
        "production_freeze", "auto_promotion_hold", "provider_data",
    ]
    assert obj.actions[-1].scope_sha256 == review.NATIVE_SCOPE
