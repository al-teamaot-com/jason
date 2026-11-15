"""One Owner plan explicitly binds DIFFERENT rollback roots per native step."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from orchestrator.pmv4_objective_scope import (
    ObjectiveAction, issue_proved_objective_step,
    verify_proved_objective_step, require_objective_step_conformance,
)
from tools.pmv4_current_grant_attestation import (
    issue_current_grant_attestation, verify_current_grant_attestation,
)
from test_pmv4_owner_objective_end_to_end import (
    AT, enrolled, enroll, observed,
)


@pytest.fixture
def mixed(enrolled):
    original = enrolled["objective"]
    steps = (
        replace(original.actions[0], rollback_sha="1" * 40),
        replace(original.actions[1], rollback_sha="2" * 40),
        replace(original.actions[2], rollback_sha="3" * 40),
        original.actions[3],  # Native Stage A0 empty baseline (global rollback).
    )
    enrolled["objective"] = replace(original, actions=steps)
    return enrolled


def test_one_owner_decision_authorizes_distinct_native_rollback_targets(mixed):
    objective = mixed["objective"]
    signed_parent = enroll(mixed)
    assert len(mixed["consents"]) == 1
    assert objective.review_material()["actions"][0]["rollback_sha"] == "1" * 40
    assert objective.review_material()["actions"][1]["rollback_sha"] == "2" * 40
    assert "rollback_sha" not in objective.review_material()["actions"][3]
    assert objective.rollback_sha == observed(objective, 3)["rollback_sha"]
    for index in range(4):
        facts = observed(objective, index)
        expected = (objective.actions[index].rollback_sha
                    or objective.rollback_sha)
        assert facts["rollback_sha"] == expected
        child = issue_proved_objective_step(
            objective=objective, ledger=mixed["ledger"],
            signed_parent=signed_parent,
            signing_key=mixed["owner_key"],
            pinned_public_key=mixed["owner_key"].public_key(),
            action_index=index, observed=facts,
            verified_prior_steps=frozenset(range(index)), at=AT,
        )
        checked = verify_proved_objective_step(
            objective=objective, ledger=mixed["ledger"],
            signed_parent=signed_parent, signed_step=child,
            pinned_public_key=mixed["owner_key"].public_key(),
            action_index=index, observed=facts,
            verified_prior_steps=frozenset(range(index)), at=AT,
        )
        assert checked["rollback_sha"] == expected
        current = issue_current_grant_attestation(
            objective=objective, signed_parent=signed_parent,
            ledger=mixed["ledger"],
            signer_private_key=mixed["owner_key"],
            pinned_public_key=mixed["owner_key"].public_key(),
            action_index=index, at=AT + timedelta(seconds=1),
        )
        assert current["payload"]["rollback_sha"] == expected
        status = verify_current_grant_attestation(
            objective=objective, signed_parent=signed_parent,
            signed_attestation=current,
            pinned_public_key=mixed["owner_key"].public_key(),
            expected_action_index=index, at=AT + timedelta(seconds=2),
        )
        assert status["step_index"] == index
    assert len(mixed["consents"]) == 1


@pytest.mark.parametrize("index", [0, 1, 2])
def test_global_rollback_cannot_substitute_for_action_exact_rollback(mixed, index):
    objective = mixed["objective"]
    enroll(mixed)
    facts = observed(objective, index)
    with pytest.raises(PermissionError, match="release candidate or production control drift"):
        require_objective_step_conformance(
            ledger=mixed["ledger"], objective=objective,
            approved_fingerprint=objective.fingerprint, action_index=index,
            observed_candidate_sha=facts["candidate_sha"],
            observed_rollback_sha=objective.rollback_sha,
            observed_freeze_sha256=facts["freeze_sha256"],
            observed_hold_sha256=facts["hold_sha256"],
            observed_scope_sha256=facts["scope_sha256"],
            observed_artifact_sha256=facts["artifact_sha256"],
            now=AT,
        )


def test_action_rollback_mutation_after_approval_rejected(mixed):
    objective = mixed["objective"]
    signed_parent = enroll(mixed)
    changed = replace(objective,
                      actions=(replace(objective.actions[0],
                                       rollback_sha="4" * 40),)
                              + objective.actions[1:])
    assert changed.fingerprint != objective.fingerprint
    with pytest.raises(PermissionError):
        issue_proved_objective_step(
            objective=changed, ledger=mixed["ledger"],
            signed_parent=signed_parent,
            signing_key=mixed["owner_key"],
            pinned_public_key=mixed["owner_key"].public_key(),
            action_index=0, observed=observed(changed, 0), at=AT,
        )
    assert len(mixed["consents"]) == 1


@pytest.mark.parametrize("bad", ["not-a-sha", "", "0" * 39, False, 23])
def test_bad_action_specific_rollback_denied_before_consent(bad):
    with pytest.raises(ValueError):
        ObjectiveAction(
            capability="pmv4.source",
            component="root-source", scope_sha256="a"*64,
            artifact_sha256="b"*64, risk=3, rollback_sha=bad,
        )
