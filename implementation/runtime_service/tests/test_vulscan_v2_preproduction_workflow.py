"""Fixture-backed preproduction checks for dormant V2 workflow composition."""
from datetime import date, datetime, timezone

import pytest

from jason_runtime.autonomy_worker_runtime import SQLiteOperationalWorkStore
from jason_runtime.vulscan_governed_patch_source import VerifiedPatchTarget, VulscanPatchEvidenceError
from jason_runtime.vulscan_microsoft_release_evidence import GovernedMicrosoftReleaseRecord
from jason_runtime.vulscan_owner_disposition_evidence import VerifiedPatchReviewDisposition
from jason_runtime.vulscan_v2_preproduction_workflow import (
    VerifiedVulscanTargetInventory, VulscanV2PreproductionWorkflow,
    VulscanV2ShadowMaintenance,
)

NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)
RELEASE = date(2026, 10, 13)


def target(*, client_id="company-12", policy_id="policy-weekly",
           device_id="ci-10", device_uid="rmm-10", hostname="PC-10",
           status_verified=True, **changes):
    props = dict(
        kb="KB5123456", client_id=client_id, policy_id=policy_id,
        device_id=device_id, device_uid=device_uid, hostname=hostname,
        identity_verified=status_verified,
        policy_kb_attribution_verified=True,
        policy_kb_attribution_reference="governed-fixture-per-policy-attribution",
        policy_kb_attribution_checked_at=NOW,
    )
    props.update(changes)
    return VerifiedPatchTarget(**props)


def release(kb):
    return GovernedMicrosoftReleaseRecord(
        kb=kb, release_date=RELEASE,
        release_source_url="https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information",
        release_source_verified=True, fetched_at=NOW,
        title="October cumulative Windows update",
        article_url="https://support.microsoft.com/help/5123456",
        article_verified=True,
        summary="Windows security update with verified fixes.",
        known_issues="A known installation issue is documented.",
        article_heading_release_date=RELEASE,
    )


def make_flow(tmp_path, *, state=None, targets=None, coverage=True,
              promoted=None, readings=None, release_reader=release,
              review_state=None, owner_decisions_available=True):
    state = state if state is not None else {"installStatus": "NOT_APPROVED"}
    readings = readings if readings is not None else []
    targets = targets if targets is not None else (target(),)
    review_state = review_state if review_state is not None else {"disposition": "review_pending"}
    def review_read(item):
        return VerifiedPatchReviewDisposition(
            kb=item.kb, client_id=item.client_id, policy_id=item.policy_id,
            device_uid=item.device_uid,
            disposition=review_state["disposition"],
            checked_at=NOW, full_scope_verified=True,
            source_reference="preproduction-governed-owner-review",
        )
    store = SQLiteOperationalWorkStore(tmp_path / "state.db")
    def read(capability, arguments):
        readings.append((capability, dict(arguments)))
        if capability == "endpoint.device.read":
            uid = arguments["resource_id"]
            endpoint = next(item for item in targets if item.device_uid == uid)
            return {"status": "succeeded", "evidence": {
                "record": {"resource_id": uid, "hostname": endpoint.hostname}}}
        if capability == "endpoint.patch.policy.search":
            return {"status": "succeeded", "evidence": {"data": {"policies": [
                {"policyUid": policy} for policy in ("policy-weekly", "policy-servers")
            ]}}}
        if capability == "endpoint.patch.search":
            return {"status": "succeeded", "evidence": {"data": {"patches": [{
                "kbArticleId": "5123456", "installStatus": state["installStatus"],
            }]}}}
        assert False, "unexpected capability"
    return VulscanV2PreproductionWorkflow(
        store=store,
        inventory_reader=lambda: VerifiedVulscanTargetInventory(
            targets=tuple(targets), full_scope_verified=coverage,
            source_reference="preproduction-governed-policy-snapshot"),
        patch_read=read, microsoft_release_reader=release_reader,
        review_disposition_read=review_read if owner_decisions_available else None,
        activation_verified=promoted,
    ), readings


def test_shadow_evaluates_without_queue_or_send(tmp_path):
    flow, reads = make_flow(tmp_path)
    result = flow.evaluate_once(now=NOW)
    assert (result.mode, result.candidate_count, result.enqueued_count) == ("shadow", 1, 0)
    assert flow.store.due_patch_approval_notifications(now=NOW) == ()
    assert [cap for cap, _ in reads] == [
        "endpoint.device.read", "endpoint.patch.policy.search", "endpoint.patch.search"
    ]


def test_enqueue_fails_before_reads_without_exact_promotion(tmp_path):
    flow, reads = make_flow(tmp_path)
    with pytest.raises(PermissionError, match="promotion"):
        flow.evaluate_once(now=NOW, enqueue=True)
    assert reads == []


def test_promoted_enqueue_stays_in_existing_outbox_not_direct_teams(tmp_path):
    flow, _ = make_flow(tmp_path, promoted=lambda: True, targets=(
        target(), target(client_id="company-99", policy_id="policy-servers",
                         device_id="ci-22", device_uid="rmm-22", hostname="SRV-22"),
    ))
    result = flow.evaluate_once(now=NOW, enqueue=True)
    assert result.mode == "queued"
    assert result.candidate_count == 1
    assert result.enqueued_count == 1
    entries = flow.store.due_patch_approval_notifications(now=NOW)
    assert len(entries) == 1
    assert entries[0]["event_type"] == "patch_approval_aging"
    assert flow.store.due_teams_notifications(now=NOW) == ()


def test_repeated_scan_does_not_duplicate_existing_event(tmp_path):
    flow, _ = make_flow(tmp_path, promoted=lambda: True)
    assert flow.evaluate_once(now=NOW, enqueue=True).enqueued_count == 1
    assert flow.evaluate_once(now=NOW, enqueue=True).enqueued_count == 1
    assert len(flow.store.due_patch_approval_notifications(now=NOW)) == 1


def test_verify_current_fail_closed_after_patch_approval(tmp_path):
    state = {"installStatus": "NOT_APPROVED"}
    flow, _ = make_flow(tmp_path, state=state, promoted=lambda: True)
    flow.evaluate_once(now=NOW, enqueue=True)
    notice = flow.store.due_patch_approval_notifications(now=NOW)[0]
    import json
    from datetime import date
    from jason_runtime.vulscan_patch_approval_notification import PreparedPatchNotification
    payload = json.loads(notice["arguments_json"])
    prepared = PreparedPatchNotification(
        kb=payload["kb"], stage=payload["stage"],
        released=date.fromisoformat(payload["released"]),
        age_days=payload["age_days"],
        policy_ids=tuple(payload["policy_ids"]),
        affected_clients=payload["affected_clients"],
        affected_devices=payload["affected_devices"],
        idempotency_key=payload["idempotency_key"],
        text=payload["text"],
    )
    assert flow.verify_current(prepared, now=NOW)
    state["installStatus"] = "APPROVED_PENDING"
    assert not flow.verify_current(prepared, now=NOW)


def test_incomplete_scoped_inventory_is_not_publishable(tmp_path):
    flow, reads = make_flow(tmp_path, coverage=False, promoted=lambda: True)
    with pytest.raises(VulscanPatchEvidenceError, match="complete"):
        flow.evaluate_once(now=NOW, enqueue=True)
    assert reads == []
    assert flow.store.due_patch_approval_notifications(now=NOW) == ()


def test_missing_official_release_evidence_blocks_notifications(tmp_path):
    def missing(kb):
        raise ValueError("official KB feed unavailable")
    flow, reads = make_flow(tmp_path, promoted=lambda: True,
                            release_reader=missing)
    with pytest.raises(ValueError, match="unavailable"):
        flow.evaluate_once(now=NOW, enqueue=True)
    assert reads == []
    assert flow.store.due_patch_approval_notifications(now=NOW) == ()


def test_not_approved_only_approved_status_no_notice(tmp_path):
    flow, _ = make_flow(tmp_path, state={"installStatus": "APPROVED_PENDING"})
    assert flow.evaluate_once(now=NOW).candidate_count == 0


def test_unverified_inventory_target_rejected(tmp_path):
    flow, reads = make_flow(tmp_path, targets=(target(status_verified=False),))
    with pytest.raises(VulscanPatchEvidenceError, match="verified"):
        flow.evaluate_once(now=NOW)
    assert reads == []


def test_auxiliary_shadow_cadence_is_read_only_and_non_spamming(tmp_path):
    flow, reads = make_flow(tmp_path)
    maintenance = VulscanV2ShadowMaintenance(
        workflow=flow,
        interval_seconds=86400,
        monotonic=iter((0.0, 60.0, 86401.0)).__next__,
        current_time=lambda: NOW,
    )
    assert maintenance.tick().candidate_count == 1
    assert maintenance.tick() is None
    assert maintenance.tick().candidate_count == 1
    assert len(reads) == 6
    assert flow.store.due_patch_approval_notifications(now=NOW) == ()


def test_auxiliary_shadow_frequency_cannot_flood(tmp_path):
    flow, _ = make_flow(tmp_path)
    with pytest.raises(ValueError, match="hourly"):
        VulscanV2ShadowMaintenance(workflow=flow, interval_seconds=5)


def test_without_authoritative_owner_disposition_no_shadow_notification(tmp_path):
    flow, reads = make_flow(tmp_path, owner_decisions_available=False)
    with pytest.raises(VulscanPatchEvidenceError, match="owner disposition"):
        flow.evaluate_once(now=NOW)
    assert reads == []


def test_owner_deferral_stops_new_notifications_and_stale_prepared_sends(tmp_path):
    from jason_runtime.vulscan_patch_approval_notification import PreparedPatchNotification
    review_state = {"disposition": "review_pending"}
    flow, reads = make_flow(tmp_path, promoted=lambda: True, review_state=review_state)
    flow.evaluate_once(now=NOW, enqueue=True)
    assert flow.store.due_patch_approval_notifications(now=NOW)
    review_state["disposition"] = "deferred"
    assert flow.evaluate_once(now=NOW).candidate_count == 0
    assert flow.store.due_patch_approval_notifications(now=NOW)
    # A pending message in the outbox must fail the authoritative readback
    # before send, even if it was eligible at the initial snapshot.
    from datetime import date
    import json
    data=json.loads(flow.store.due_patch_approval_notifications(now=NOW)[0]["arguments_json"])
    prepared=PreparedPatchNotification(
        kb=data["kb"], stage=data["stage"],
        released=date.fromisoformat(data["released"]),
        age_days=data["age_days"],
        policy_ids=tuple(data["policy_ids"]),
        affected_clients=data["affected_clients"],
        affected_devices=data["affected_devices"],
        idempotency_key=data["idempotency_key"], text=data["text"],
    )
    assert flow.verify_current(prepared, now=NOW) is False
