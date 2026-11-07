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
