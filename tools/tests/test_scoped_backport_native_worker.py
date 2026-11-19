"""Root consumer, Owner auth and crash recovery are closed from checkout."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path

import pytest

from tools import scoped_backport_native_root as worker
from tools import scoped_backport_native_recovery as recovery
from tools import scoped_backport_owner_local_approval as owner
from tools import scoped_backport_release as core

ROOT = Path(__file__).resolve().parents[2]
M = json.loads((ROOT / core.RELEASE_MANIFEST).read_text())
MAIN = "510243494efcd592a1585c681a3fa28a29296e17"
OFFER = core.make_offer(M, main_sha=MAIN)


def test_root_worker_denies_uninstalled_checkout_before_provider_or_docker():
    with pytest.raises(core.ScopedBackportDenied,
                       match="INSTALLED_NATIVE_ROOT_WORKER_REQUIRED"):
        worker.dispatch_one("f" * 32)


def test_root_worker_cli_denies_source_checkout_even_with_drain(monkeypatch):
    monkeypatch.setattr(worker.os, "geteuid", lambda: 0)
    with pytest.raises(core.ScopedBackportDenied,
                       match="INSTALLED_NATIVE_ROOT_WORKER_REQUIRED"):
        worker.drain()


def test_owner_approval_denies_source_checkout_before_any_entra_request():
    with pytest.raises(core.ScopedBackportDenied):
        owner.approve("release-87dfd07ae67d2d99")


def test_recovery_denies_source_checkout_before_mutation():
    with pytest.raises(core.ScopedBackportDenied,
                       match="INSTALLED_ROOT_RECOVERY_TIMER_REQUIRED"):
        recovery.reconcile_all()


def test_root_typed_request_requires_exact_canonical_offer_hash():
    from tools.scoped_backport_release_request import request
    req = request("scoped_backport_promote", OFFER, offer_sha256="f" * 64)
    with pytest.raises(core.ScopedBackportDenied,
                       match="NATIVE_BACKPORT_OFFER_HASH_MISMATCH"):
        worker._verify_typed_request(req, OFFER)


@pytest.mark.parametrize("action", ["scoped_backport_stage", "scoped_backport_promote",
                                    "scoped_backport_recover"])
def test_root_request_exact_fields_matched(action):
    from tools.scoped_backport_release_request import request
    offer_hash = core.sha256(core.canonical(OFFER)).hexdigest()
    req = request(action, OFFER,
                  offer_sha256=offer_hash if action != "scoped_backport_stage" else None)
    assert worker._verify_typed_request(req, OFFER) == action


def test_root_request_rejects_forged_client():
    from tools.scoped_backport_release_request import request
    req = request("scoped_backport_stage", OFFER)
    req["client_id"] = "other-tenant"
    with pytest.raises(core.ScopedBackportDenied,
                       match="NATIVE_BACKPORT_REQUEST_SCOPE_DRIFT"):
        worker._verify_typed_request(req, OFFER)


class StageHost:
    def __init__(self):
        self.root = Path("/not-mounted")
        self.actions = []
    def release_lock(self, offer):
        self.actions.append("lock")
        return nullcontext()
    def freshly_validate_live_scope(self, offer): self.actions.append("fresh")
    def ensure_breaker_closed_and_workers_quiescent(self): self.actions.append("breaker")
    def deny_unresolved_attempt(self, offer): self.actions.append("unique")


def test_stage_requires_live_scope_and_native_preflight_before_publishing(monkeypatch):
    host = StageHost()
    published = []
    monkeypatch.setattr(worker, "_native_preflight",
                        lambda offer, h: host.actions.append("preflight"))
    monkeypatch.setattr(worker, "atomic_root_json",
                        lambda path, doc: published.append(("root", path, doc)))
    monkeypatch.setattr(worker, "_publish_public",
                        lambda name, key, doc: published.append((name, key, doc)))
    eligibility = worker.stage(host, OFFER)
    assert host.actions == ["lock", "fresh", "breaker", "unique", "preflight"]
    assert eligibility["status"] == "native_scoped_preproduction_eligible_not_approved"
    assert eligibility["owner_approval_recorded"] is False
    assert eligibility["production_mutations"] is False
    assert eligibility["provider_writes"] is False
    assert [item[0] for item in published] == ["root", "offers", "eligibility"]
    assert all("signed_owner_proof" not in str(item) for item in published)


def test_promote_requires_identical_root_and_public_eligible_receipt(monkeypatch):
    receipt = {"release_id": OFFER["release_id"],
               "status": "native_scoped_preproduction_eligible_not_approved",
               "manifest_sha256": OFFER["manifest_sha256"]}
    host = StageHost()
    signed = {"release_id": OFFER["release_id"],
              "candidate_sha": OFFER["candidate_sha"],
              "manifest_sha256": OFFER["manifest_sha256"],
              "standing_authority": False,
              "signed_owner_proof": {"one_time": "test"}}
    monkeypatch.setattr(worker, "root_json", lambda *args, **kwargs:
                        {"source_offer": OFFER, "eligible": receipt})
    monkeypatch.setattr(worker, "_public_json", lambda name, release_id:
                        receipt if name == "eligibility" else signed)
    calls = []
    monkeypatch.setattr(worker, "governed_promote", lambda o, proof, host:
                        (calls.append((o, proof)), {"status": "verified"})[1])
    assert worker.promote(host, OFFER)["status"] == "verified"
    assert len(calls) == 1 and calls[0][1] == signed["signed_owner_proof"]


def test_public_eligible_receipt_mutation_denies_before_promotion(monkeypatch):
    host = StageHost()
    receipt = {"status": "native_scoped_preproduction_eligible_not_approved",
               "release_id": OFFER["release_id"],
               "manifest_sha256": OFFER["manifest_sha256"]}
    altered = dict(receipt, status="owner_approved")
    monkeypatch.setattr(worker, "root_json", lambda *args, **kwargs:
                        {"source_offer": OFFER, "eligible": receipt})
    monkeypatch.setattr(worker, "_public_json", lambda *args, **kwargs: altered)
    with pytest.raises(core.ScopedBackportDenied,
                       match="PUBLIC_SCOPED_ELIGIBILITY_REPLACED"):
        worker.promote(host, OFFER)


class RecoverHost:
    def __init__(self):
        self.actions = []
        self.active_offer = None
    def release_lock(self, offer):
        self.actions.append("lock")
        return nullcontext()
    def open_breaker(self, reason):
        self.actions.append("breaker")
    def restore_pair_exact(self, offer): self.actions.append("restore")
    def verify_rollback(self, offer): self.actions.append("verify_images")
    def verify_protected_unchanged(self, before):
        self.actions.append("verify_other")
    def _journal_update(self, offer, status, **kwargs):
        self.actions.append("journal_" + status)


def test_interrupted_root_transaction_rolls_back_and_opens_breaker(monkeypatch):
    host = RecoverHost()
    doc = {
        "release_id": OFFER["release_id"],
        "candidate_sha": OFFER["candidate_sha"],
        "rollback_sha": OFFER["rollback_sha"],
        "scope_sha256": OFFER["scope_sha256"],
        "manifest_sha256": OFFER["manifest_sha256"],
        "outcome": "",
        "protected_before": {name: {"id": "unchanged"}
                             for name in core.PROTECTED},
    }
    monkeypatch.setattr(recovery, "_restore_frozen_backup",
                        lambda host, offer: host.actions.append("refreeze"))
    report = recovery.reconcile_one(host, OFFER, doc)
    assert report["status"] == "interrupted_rollback_verified_breaker_open"
    assert host.actions == ["lock", "breaker", "restore", "verify_images",
                            "verify_other", "refreeze",
                            "journal_interrupted_rollback_verified"]


def test_already_resolved_root_journal_never_mutates(monkeypatch):
    host = RecoverHost()
    doc = {
        "release_id": OFFER["release_id"],
        "candidate_sha": OFFER["candidate_sha"],
        "rollback_sha": OFFER["rollback_sha"],
        "scope_sha256": OFFER["scope_sha256"],
        "manifest_sha256": OFFER["manifest_sha256"],
        "outcome": "production_pair_verified",
    }
    assert recovery.reconcile_one(host, OFFER, doc)["status"] == (
        "resolved_prior_attempt_no_action")
    assert host.actions == []


def test_foreign_recovery_journal_denied_before_root_state(monkeypatch):
    host = RecoverHost()
    doc = {"release_id": "release-" + "c" * 16}
    with pytest.raises(core.ScopedBackportDenied, match="RECOVERY_JOURNAL_OFFER_MISMATCH"):
        recovery.reconcile_one(host, OFFER, doc)
    assert host.actions == []
