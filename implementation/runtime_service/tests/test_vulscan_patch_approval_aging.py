from datetime import date, timedelta

from jason_runtime.vulscan_patch_approval_aging import (
    PatchApprovalObservation, evaluate_approval_aging,
)


def obs(age=16, **kw):
    values = dict(
        kb="KB5123456", release_date=date(2026, 10, 1),
        observed_date=date(2026, 10, 1) + timedelta(days=age),
        policy_id="workstations", client_id="client-a", device_id="device-1",
        approval_state="NOT_APPROVED", source_verified=True,
    )
    values.update(kw)
    return PatchApprovalObservation(**values)


def test_normal_grace_period():
    assert evaluate_approval_aging([obs(15)]) == ()


def test_day_16_and_day_21():
    assert evaluate_approval_aging([obs(16)])[0].stage == "day16_notice"
    assert evaluate_approval_aging([obs(21)])[0].stage == "day21_escalation"


def test_approved_deferred_and_superseded_do_not_notify():
    assert evaluate_approval_aging([obs(21, approval_state="APPROVED")]) == ()
    assert evaluate_approval_aging([obs(21, intentional_deferral=True)]) == ()
    assert evaluate_approval_aging([obs(21, superseded=True)]) == ()


def test_urgent_review_bypasses_grace_not_authority():
    assert evaluate_approval_aging([obs(1, actively_exploited=True)])[0].stage == "urgent_review"


def test_same_policy_aggregates_and_dedupes_devices():
    decisions = evaluate_approval_aging([
        obs(), obs(device_id="device-1"), obs(client_id="client-b", device_id="device-2")
    ])
    assert len(decisions) == 1
    assert decisions[0].affected_clients == 2
    assert decisions[0].affected_devices == 2


def test_different_policy_separates_decisions():
    assert len(evaluate_approval_aging([obs(), obs(policy_id="servers")])) == 2


def test_unknown_or_disputed_release_date_fails_to_evidence_exception():
    assert evaluate_approval_aging([obs(release_date=None)])[0].stage == "evidence_exception"
    assert evaluate_approval_aging([
        obs(), obs(release_date=date(2026, 9, 30))
    ])[0].stage == "evidence_exception"


def test_no_backdated_release_on_future_publication():
    assert evaluate_approval_aging([obs(age=-1)])[0].stage == "evidence_exception"


def test_bad_patch_identity_fails_closed():
    try:
        evaluate_approval_aging([obs(kb="not-a-kb")])
    except ValueError:
        pass
    else:
        assert False, "invalid KB must be rejected"
