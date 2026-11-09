"""PMv3.2 one signed Teams click -> two narrow receipts -> native safe freeze lifecycle.

Runs only against disposable tmp_path; no real Teams, production marker or provider.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "pmv32_one_teams_host_runner", ROOT / "tools/release_manager_host_runner.py"
)
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

SHA = "a" * 40
ROLLBACK = "b" * 40
RID = "release-" + SHA[:16]
APPROVAL_ID = "relapproval-" + "c" * 32
SIGNED_SHA = "d" * 64
SCOPE = "e" * 64


def scenario(tmp_path: Path):
    marker = tmp_path / runner.PRODUCTION_FREEZE_MARKER
    raw = (json.dumps({
        "schema_version": "1.0",
        "status": "active",
        "scope": "manual-and-automatic-production-promotions",
        "remove_only_after": "new explicit exact-SHA owner unfreeze decision",
    }) + "\n").encode("utf-8")
    marker.write_bytes(raw)
    marker.chmod(0o600)
    manifest = {
        "candidate_sha": SHA,
        "rollback_sha": ROLLBACK,
        "changed_files": ["tools/production_drift_guard.py"],
    }
    record = {
        "release_id": RID, "state": "production_eligible",
        "rollback_sha": ROLLBACK,
        "release_candidate": {"candidate_sha": SHA},
        "release_manifest": manifest,
        "manual_scope_review": {
            "schema_version": "1.0", "candidate_sha": SHA,
            "baseline_sha": ROLLBACK, "scope_sha256": SCOPE,
        },
        "owner_approval": {
            "approved": True, "candidate_sha": SHA,
            "source": "authenticated_mobile_teams_owner:" + APPROVAL_ID,
        },
        "history": [],
    }
    runner.atomic_json(tmp_path / "records" / (RID + ".json"), record)
    binding = runner.current_initial_freeze_binding(tmp_path, record)
    assert binding["freeze_sha256"] == hashlib.sha256(raw).hexdigest()
    runner.atomic_json(tmp_path / "mobile-release-offers" / (RID + ".json"), {
        "release_id": RID, "candidate_sha": SHA,
        "live_rollback_sha": ROLLBACK,
        "manifest_sha256": binding["manifest_sha256"],
        "initial_freeze_binding": binding,
    })
    decision = datetime.now(timezone.utc)
    return marker, raw, record, binding, {
        "release_id": RID, "candidate_sha": SHA,
        "approval_id": APPROVAL_ID,
        "signed_evidence_sha256": SIGNED_SHA,
        "request_metadata": {
            "release_id": RID, "candidate_sha": SHA, "rollback_sha": ROLLBACK,
            "manifest_sha256": binding["manifest_sha256"],
            "initial_freeze_binding": binding,
        },
        "decided_at": decision,
        "expires_at": decision + timedelta(minutes=7),
    }


def record_grant(tmp_path, args):
    with patch.object(runner, "verify_candidate_on_main"), \
         patch.object(runner, "require_current_manual_scope_review"), \
         patch.object(runner, "revalidate_circuit_breaker"), \
         patch.object(runner, "live_production_alignment"):
        return runner.record_signed_initial_unfreeze(ROOT, tmp_path, **args)


def test_one_signed_click_produces_separate_exact_receipt_and_restores_freeze(tmp_path):
    marker, raw, record, binding, args = scenario(tmp_path)
    doc = record_grant(tmp_path, args)
    assert marker.read_bytes() == raw  # signing can NEVER unfreeze live production
    assert doc["authorization"] == "signed_teams_initial_unfreeze"
    assert doc["automatic_publish_authority"] is False
    assert doc["standing_authority"] is False
    loaded = runner.load_record(tmp_path, RID)
    assert loaded["owner_approval"] == record["owner_approval"]
    ctx = runner.explicit_owner_one_transaction_freeze_context(tmp_path, loaded)
    assert ctx is not None
    assert ctx["authorization"] == "signed_teams_initial_unfreeze"
    opened = runner.begin_one_transaction_freeze_exception(tmp_path, ctx)
    assert not marker.exists()
    tx = json.loads(opened["receipt_path"].read_text())
    assert tx["explicit_unfreeze_receipt_sha256"] == ctx["explicit_unfreeze_receipt_sha256"]
    runner.restore_one_transaction_freeze_exception(tmp_path, opened, release_state="closed")
    assert marker.read_bytes() == raw
    source_path = tmp_path / "owner-signed-unfreeze-receipts" / (RID + ".json")
    assert json.loads(source_path.read_text())["status"] == "consumed"
    assert runner.explicit_owner_one_transaction_freeze_context(
        tmp_path, runner.load_record(tmp_path, RID)) is None
    with pytest.raises(runner.ReleaseManagerError):
        runner.begin_one_transaction_freeze_exception(tmp_path, ctx)
    assert marker.read_bytes() == raw


def test_one_signed_click_is_idempotent_before_transaction(tmp_path):
    marker, raw, record, binding, args = scenario(tmp_path)
    first = record_grant(tmp_path, args)
    path = tmp_path / "owner-signed-unfreeze-receipts" / (RID + ".json")
    original_bytes = path.read_bytes()
    record_bytes = (tmp_path / "records" / (RID + ".json")).read_bytes()
    again = record_grant(tmp_path, args)
    assert again == first
    assert path.read_bytes() == original_bytes
    assert (tmp_path / "records" / (RID + ".json")).read_bytes() == record_bytes


@pytest.mark.parametrize("tamper", ["wrong_scope", "wrong_rollback", "wrong_freeze", "wrong_approval"])
def test_signed_one_click_rejects_tampered_subject_before_any_unfreeze(tmp_path, tamper):
    marker, raw, record, binding, args = scenario(tmp_path)
    if tamper == "wrong_scope":
        args["request_metadata"]["initial_freeze_binding"] = dict(binding, scope_sha256="0" * 64)
    elif tamper == "wrong_rollback":
        args["request_metadata"]["rollback_sha"] = "0" * 40
    elif tamper == "wrong_freeze":
        marker.write_bytes(raw + b" ")
        marker.chmod(0o600)
    else:
        args["approval_id"] = "relapproval-" + "f" * 32
    with pytest.raises(runner.ReleaseManagerError):
        record_grant(tmp_path, args)
    assert not (tmp_path / "owner-signed-unfreeze-receipts" / (RID + ".json")).exists()
    assert not (tmp_path / "owner-unfreeze-receipts" / (RID + ".json")).exists()
    assert marker.exists()


def test_modified_or_expired_signed_receipt_cannot_lift_freeze(tmp_path):
    marker, raw, record, binding, args = scenario(tmp_path)
    record_grant(tmp_path, args)
    loaded = runner.load_record(tmp_path, RID)
    path = tmp_path / "owner-signed-unfreeze-receipts" / (RID + ".json")
    source = json.loads(path.read_text())
    source["scope_sha256"] = "1" * 64
    runner.atomic_json(path, source)
    assert runner.explicit_owner_one_transaction_freeze_context(tmp_path, loaded) is None
    assert marker.read_bytes() == raw
    # Recreate original source, but explicit expiry still invalidates it.
    assert runner.explicit_owner_one_transaction_freeze_context(tmp_path, loaded) is None


def test_crash_restores_original_freeze_and_consumes_signed_one_click(tmp_path):
    marker, raw, record, binding, args = scenario(tmp_path)
    record_grant(tmp_path, args)
    ctx = runner.explicit_owner_one_transaction_freeze_context(
        tmp_path, runner.load_record(tmp_path, RID))
    opened = runner.begin_one_transaction_freeze_exception(tmp_path, ctx)
    assert not marker.exists()
    with pytest.raises(runner.ReleaseManagerError, match="restored production freeze"):
        runner.restore_stranded_one_transaction_freeze_under_lock(tmp_path)
    assert marker.read_bytes() == raw
    source = tmp_path / "owner-signed-unfreeze-receipts" / (RID + ".json")
    assert json.loads(source.read_text())["status"] == "consumed"
    assert json.loads(opened["receipt_path"].read_text())["freeze_restored"] is True
    assert runner.explicit_owner_one_transaction_freeze_context(
        tmp_path, runner.load_record(tmp_path, RID)) is None


def test_expired_card_never_records_unfreeze(tmp_path):
    marker, raw, record, binding, args = scenario(tmp_path)
    args["decided_at"] = datetime.now(timezone.utc) - timedelta(minutes=21)
    args["expires_at"] = args["decided_at"] + timedelta(minutes=7)
    with pytest.raises(runner.ReleaseManagerError, match="invalid or expired"):
        record_grant(tmp_path, args)
    assert marker.read_bytes() == raw
    assert not (tmp_path / "owner-signed-unfreeze-receipts").exists()



def test_host_approval_offer_binds_frozen_transaction_once_and_republishes_on_marker_change(
    tmp_path, monkeypatch,
):
    from types import SimpleNamespace
    import release_mobile_approval_consumer as mobile_consumer
    import jason_runtime.mobile_release_approval as mobile_policy
    import jason_runtime.owner_release_approval_containment as containment

    marker, raw, record, binding, args = scenario(tmp_path)
    (tmp_path / "auto-promotion-incident-hold").touch()
    offer_path = tmp_path / "mobile-release-offers" / (RID + ".json")
    offer_path.unlink()
    record["risk_profile"] = "normal"
    record["owner_approval"] = {"approved": False}
    record["preproduction"] = {
        "acceptance_passed": True, "rollback_readiness_passed": True,
    }
    record["development"] = {"required_checks_passed": True}
    runner.atomic_json(tmp_path / "records" / (RID + ".json"), record)
    policy_path = tmp_path / "private-mobile-policy.json"
    policy_path.write_text("{}")
    live = {"revision": ROLLBACK, "inspect": {
        "Config": {"Env": ["JASON_RELEASE_MOBILE_APPROVAL_MODE=owner_reviewed"]}
    }}
    control = {"schema_version": "1.0", "circuit_breaker": {"state": "closed"},
               "last_known_good": {"manifest": {"revision": ROLLBACK}}}
    drift = {"schema_version": "1.0", "status": "pass", "problems": []}
    reviewed = SimpleNamespace(
        schema_version="2.0", allowed_risk_profiles=frozenset({"normal"}),
    )
    with patch.object(runner, "DEFAULT_STATE", tmp_path), \
         patch.object(runner, "MOBILE_APPROVAL_POLICY", policy_path), \
         patch.object(runner, "_read_protected_snapshot",
                      side_effect=lambda state, name: (
                          control if name == "production-control-state.json" else drift)), \
         patch.object(runner, "live_runtime", return_value=live), \
         patch.object(runner, "live_production_alignment"), \
         patch.object(runner, "require_current_manual_scope_review"), \
         patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA), \
         patch.object(mobile_consumer, "_install_repo_modules"), \
         patch.object(mobile_consumer, "consume_mobile_release_decisions"), \
         patch.object(mobile_policy, "read_mobile_release_policy", return_value=reviewed), \
         patch.object(containment, "read_release_approval_containment",
                      return_value=SimpleNamespace(active=False)), \
         patch.object(runner, "deploy_production") as deploy:
        assert runner.approval_only_while_promotion_held(ROOT, tmp_path)
        first = json.loads(offer_path.read_text())
        assert first["initial_freeze_binding"] == binding
        assert first["protected_main_sha"] == SHA
        assert runner.approval_only_while_promotion_held(ROOT, tmp_path) is False
        assert json.loads(offer_path.read_text()) == first

        # A changed freeze invalidates the old Teams subject; do not approve
        # an old card against the new state or silently extend old authority.
        marker.write_bytes(raw + b" ")
        marker.chmod(0o600)
        assert runner.approval_only_while_promotion_held(ROOT, tmp_path)
        new = json.loads(offer_path.read_text())
        assert new["initial_freeze_binding"]["freeze_sha256"] != binding["freeze_sha256"]
        assert new["initial_freeze_binding"]["scope_sha256"] == binding["scope_sha256"]
        deploy.assert_not_called()


def test_legacy_nonfreeze_offer_is_not_incorrectly_rejected_by_umask(tmp_path):
    from jason_runtime.mobile_release_approval import _host_offered_initial_freeze
    marker, raw, record, binding, args = scenario(tmp_path)
    offer = tmp_path / "mobile-release-offers" / (RID + ".json")
    offer.chmod(0o664)
    with pytest.raises(PermissionError, match="unsafe write permissions"):
        _host_offered_initial_freeze(
            tmp_path, RID, SHA, ROLLBACK,
            binding["manifest_sha256"], binding["scope_sha256"],
        )
    legacy = json.loads(offer.read_text())
    legacy.pop("initial_freeze_binding")
    offer.write_text(json.dumps(legacy))
    assert _host_offered_initial_freeze(
        tmp_path, RID, SHA, ROLLBACK,
        binding["manifest_sha256"], binding["scope_sha256"],
    ) is None


def test_governed_retry_release_uses_same_single_approval_contract(tmp_path):
    marker, raw, record, binding, args = scenario(tmp_path)
    retry_id = RID + "-retry-1"
    record["release_id"] = retry_id
    runner.atomic_json(tmp_path / "records" / (retry_id + ".json"), record)
    # The issued Teams request and protected host offer both identify the
    # governed retry record, never the superseded original release ID.
    new_binding = runner.current_initial_freeze_binding(tmp_path, record)
    assert new_binding["release_id"] == retry_id
    offer = {
        "release_id": retry_id,
        "candidate_sha": SHA,
        "live_rollback_sha": ROLLBACK,
        "manifest_sha256": new_binding["manifest_sha256"],
        "initial_freeze_binding": new_binding,
    }
    runner.atomic_json(tmp_path / "mobile-release-offers" / (retry_id + ".json"), offer)
    args["release_id"] = retry_id
    args["request_metadata"]["release_id"] = retry_id
    args["request_metadata"]["initial_freeze_binding"] = new_binding
    grant = record_grant(tmp_path, args)
    assert grant["release_id"] == retry_id
    retry_record = runner.load_record(tmp_path, retry_id)
    assert retry_record["owner_approval"] == record["owner_approval"]
    context = runner.explicit_owner_one_transaction_freeze_context(tmp_path, retry_record)
    assert context is not None
    opened = runner.begin_one_transaction_freeze_exception(tmp_path, context)
    assert not marker.exists()
    runner.restore_one_transaction_freeze_exception(tmp_path, opened, release_state="closed")
    assert marker.read_bytes() == raw
    assert json.loads((
        tmp_path / "owner-signed-unfreeze-receipts" / (retry_id + ".json")
    ).read_text())["status"] == "consumed"


@pytest.mark.parametrize("bad_id", [
    RID + "-retry-0", RID + "-retry-001", RID + "-retry-1000", RID + "-extra",
])
def test_one_click_frozen_release_rejects_malformed_retry_name(tmp_path, bad_id):
    _, _, record, _, _ = scenario(tmp_path)
    record["release_id"] = bad_id
    assert not runner.one_transaction_release_id_matches_candidate(bad_id, SHA)
    with pytest.raises(runner.ReleaseManagerError, match="exact scope not reviewed"):
        runner.current_initial_freeze_binding(tmp_path, record)



class _SignedRenewalFutureClock(datetime):
    """Disposable fixture time: original 7-minute signed window is expired."""
    @classmethod
    def now(cls, tz=None):
        fixed = datetime.now(timezone.utc) + timedelta(minutes=8)
        return fixed if tz is None else fixed.astimezone(tz)


def _expired_initial_renewal_case(tmp_path, monkeypatch):
    import jason_runtime.mobile_release_approval as mobile
    marker, raw, _, binding, args = scenario(tmp_path)
    record_grant(tmp_path, args)
    original_path = tmp_path / "owner-signed-unfreeze-receipts" / (RID + ".json")
    original_bytes = original_path.read_bytes()
    monkeypatch.setattr(runner, "datetime", _SignedRenewalFutureClock)
    monkeypatch.setattr(mobile, "datetime", _SignedRenewalFutureClock)
    loaded = runner.load_record(tmp_path, RID)
    lineage = mobile.read_expired_initial_unfreeze_predecessor(
        tmp_path, RID, loaded,
    )
    offer = tmp_path / "mobile-release-offers" / (RID + ".json")
    runner.atomic_json(offer, {
        "schema_version": "1.0",
        "release_id": RID, "candidate_sha": SHA,
        "live_rollback_sha": ROLLBACK,
        "manifest_sha256": binding["manifest_sha256"],
        "initial_unfreeze_renewal_only": True,
        "initial_unfreeze_renewal_lineage": lineage,
        "initial_freeze_binding": binding,
    })
    renewal_id = "relapproval-" + "f" * 32
    decision = _SignedRenewalFutureClock.now(timezone.utc)
    renewal = {
        "release_id": RID, "candidate_sha": SHA,
        "approval_id": renewal_id,
        "signed_evidence_sha256": "9" * 64,
        "request_metadata": {
            "release_id": RID, "candidate_sha": SHA,
            "rollback_sha": ROLLBACK,
            "manifest_sha256": binding["manifest_sha256"],
            "initial_unfreeze_renewal_only": True,
            "initial_unfreeze_renewal_lineage": lineage,
            "initial_freeze_binding": binding,
        },
        "decided_at": decision,
        "expires_at": decision + timedelta(minutes=7),
    }
    return marker, raw, original_path, original_bytes, lineage, renewal


def _record_signed_renewal(tmp_path, args):
    with patch.object(runner, "verify_candidate_on_main"), \
         patch.object(runner, "require_current_manual_scope_review"), \
         patch.object(runner, "revalidate_circuit_breaker"), \
         patch.object(runner, "live_production_alignment"):
        return runner.record_signed_initial_unfreeze_renewal(
            ROOT, tmp_path, **args,
        )


def test_expired_signed_window_requires_distinct_new_teams_decision(tmp_path, monkeypatch):
    marker, raw, prior, prior_raw, lineage, renewal = (
        _expired_initial_renewal_case(tmp_path, monkeypatch)
    )
    assert runner.explicit_owner_one_transaction_freeze_context(
        tmp_path, runner.load_record(tmp_path, RID)
    ) is None  # The expired original is NEVER execution authority.
    doc = _record_signed_renewal(tmp_path, renewal)
    assert doc["authorization"] == "signed_teams_initial_unfreeze_renewal"
    assert doc["original_initial_unfreeze_lineage"] == lineage
    assert prior.read_bytes() == prior_raw
    assert marker.read_bytes() == raw
    saved = runner.load_record(tmp_path, RID)
    assert saved["owner_approval"]["source"].endswith(APPROVAL_ID)
    ctx = runner.explicit_owner_one_transaction_freeze_context(tmp_path, saved)
    assert ctx["authorization"] == "signed_teams_initial_unfreeze_renewal"
    assert ctx["renewal_approval_id"] == renewal["approval_id"]
    opened = runner.begin_one_transaction_freeze_exception(tmp_path, ctx)
    assert not marker.exists()
    assert opened["receipt_path"].name.endswith(renewal["approval_id"] + ".json")
    runner.restore_one_transaction_freeze_exception(
        tmp_path, opened, release_state="closed",
    )
    assert marker.read_bytes() == raw
    assert prior.read_bytes() == prior_raw
    saved_renewal = tmp_path / "owner-signed-initial-unfreeze-renewals" / (
        RID + "--" + renewal["approval_id"] + ".json"
    )
    assert json.loads(saved_renewal.read_text())["status"] == "consumed"
    assert runner.explicit_owner_one_transaction_freeze_context(
        tmp_path, runner.load_record(tmp_path, RID)
    ) is None  # One transaction only, never replay.


@pytest.mark.parametrize("tamper", [
    "wrong_scope", "wrong_rollback", "wrong_approval", "wrong_predecessor",
    "changed_freeze", "altered_original_receipt",
])
def test_expired_initial_renewal_rejects_changed_subject(
    tmp_path, monkeypatch, tamper,
):
    marker, raw, original, original_bytes, _, approval = (
        _expired_initial_renewal_case(tmp_path, monkeypatch)
    )
    if tamper == "wrong_scope":
        approval["request_metadata"]["initial_freeze_binding"] = {
            **approval["request_metadata"]["initial_freeze_binding"],
            "scope_sha256": "a" * 64,
        }
    elif tamper == "wrong_rollback":
        approval["request_metadata"]["rollback_sha"] = "0" * 40
    elif tamper == "wrong_approval":
        approval["approval_id"] = "not-a-real-id"
    elif tamper == "wrong_predecessor":
        approval["request_metadata"]["initial_unfreeze_renewal_lineage"] = {
            **approval["request_metadata"]["initial_unfreeze_renewal_lineage"],
            "predecessor_receipt_sha256": "0" * 64,
        }
    elif tamper == "changed_freeze":
        marker.write_bytes(raw + b" ")
        marker.chmod(0o600)
    else:
        original.write_bytes(original_bytes + b" ")
        original.chmod(0o600)
    with pytest.raises(runner.ReleaseManagerError):
        _record_signed_renewal(tmp_path, approval)
    assert not (tmp_path / "owner-signed-initial-unfreeze-renewals").exists()
    assert not (tmp_path / "owner-unfreeze-receipts").exists()
    assert marker.exists()


def test_signed_initial_renewal_duplicate_decision_is_idempotent(tmp_path, monkeypatch):
    marker, raw, original, original_bytes, _, approval = (
        _expired_initial_renewal_case(tmp_path, monkeypatch)
    )
    first = _record_signed_renewal(tmp_path, approval)
    second = _record_signed_renewal(tmp_path, approval)
    assert first == second
    assert original.read_bytes() == original_bytes
    assert marker.read_bytes() == raw
    other = {**approval, "approval_id": "relapproval-" + "8" * 32}
    with pytest.raises(runner.ReleaseManagerError):
        _record_signed_renewal(tmp_path, other)


def test_initial_renewal_expires_and_fails_closed(tmp_path, monkeypatch):
    import jason_runtime.mobile_release_approval as mobile
    marker, raw, original, old_raw, _, approval = (
        _expired_initial_renewal_case(tmp_path, monkeypatch)
    )
    _record_signed_renewal(tmp_path, approval)
    class ExpiredAgain(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime.now(timezone.utc) + timedelta(minutes=25)
            return fixed if tz is None else fixed.astimezone(tz)
    monkeypatch.setattr(runner, "datetime", ExpiredAgain)
    monkeypatch.setattr(mobile, "datetime", ExpiredAgain)
    assert runner.explicit_owner_one_transaction_freeze_context(
        tmp_path, runner.load_record(tmp_path, RID)
    ) is None
    assert marker.read_bytes() == raw
    assert original.read_bytes() == old_raw



def test_approval_only_purpose_recognizes_unused_expired_initial_receipt(
    tmp_path, monkeypatch,
):
    from jason_runtime.mobile_release_approval import MobileReleasePolicy
    marker, raw, original, original_raw, _, _ = (
        _expired_initial_renewal_case(tmp_path, monkeypatch)
    )
    ccc = tmp_path / "ccc"
    ccc.mkdir()
    (ccc / ("material-review-" + SHA[:16] + ".json")).write_text(
        json.dumps({
            "source_revision": SHA, "recorded_by": "person-al",
            "status": "approved",
        })
    )
    record = runner.load_record(tmp_path, RID)
    record["risk_profile"] = "normal"
    runner.save_record(tmp_path, record)
    policy = MobileReleasePolicy(
        "aot", ("person-al",),
        frozenset({"normal", "production_control_core"}),
        600, "a" * 64, "2.0",
    )
    assert runner.signed_owner_offer_purpose(
        record, SHA, policy, "owner_reviewed",
        ccc_root=ccc, state_root=tmp_path,
    ) == "initial_unfreeze_renewal_only"
    assert marker.read_bytes() == raw
    assert original.read_bytes() == original_raw
    record["renewed_initial_unfreeze_authorization"] = {
        "approval_id": "relapproval-" + "f" * 32,
    }
    assert runner.signed_owner_offer_purpose(
        record, SHA, policy, "owner_reviewed",
        ccc_root=ccc, state_root=tmp_path,
    ) is None
