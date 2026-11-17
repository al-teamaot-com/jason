"""Offline exact root-only owner proof, one-use approval and rollback tests."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import pytest

from tools import catalog_scoped_root_install_plan as p
from tools import catalog_scoped_root_install_transaction as t
from tools.tests.test_catalog_scoped_root_install_plan import MAIN, BASE, FREEZE, fake_offer


@pytest.fixture
def plan(monkeypatch):
    offered = fake_offer()
    monkeypatch.setattr(p,"repo_revision",lambda repo:MAIN)
    monkeypatch.setattr(p,"load_manifest",lambda repo,main_sha:{"rollback_sha":BASE,"freeze_sha256":FREEZE})
    monkeypatch.setattr(p,"historical_receipt_verified",lambda *args:None)
    monkeypatch.setattr(p,"make_offer",lambda *args:offered)
    monkeypatch.setattr(p,"source_git",lambda repo,*args:("protected:"+str(args)).encode())
    return p.build_install_plan(Path("/tmp/unused"),{},{},
        {"rollback_host_revision":BASE,"freeze_sha256":FREEZE,
        "root_worker_before_sha256":"1"*64,
        "pinned_owner_pubkey_file_sha256":"2"*64,
        "root_state_readback_required":True,"live_root_install_verified":False},
        expected_source_sha=MAIN)


def evidence(plan):
    oid="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
    return {
        "schema_version":"1.0", "action":t.ACTION,
        "approval_id":"catalog-root-owner-"+uuid4().hex,
        "release_id":"release-"+plan["source_sha"][:16],
        "source_sha":plan["source_sha"],
        "scope_sha256":plan["installation_scope_sha256"],
        "manifest_sha256":plan["install_plan_sha256"],
        "rollback_source_sha":plan["rollback_source_sha"],
        "freeze_sha256":plan["freeze_sha256"],
        "owner_tenant":t.TID,"owner_oid":oid,
        "owner_principal":"person-entra-"+oid.replace("-",""),
        "assurance":"fresh_verified_entra_device_code_signed_jwt",
        "verified_access_token_sha256":"a"*64,
        "approved_at":datetime.now(timezone.utc).isoformat(),
        "affirmative_decision":t.CONFIRM,
        "one_use":True,"standing_authority":False,
        "provider_write_approved":False,
    }


class FakeRoot:
    def __init__(self,auth,*,fail_at=None,rollback_broken=False):
        self.auth=auth
        self.fail_at=fail_at
        self.rollback_broken=rollback_broken
        self.events=[]
        self.consumed=set()
        self.installed=False
        self.breaker=[]
    def action(self,name):
        self.events.append(name)
        if name==self.fail_at:
            self.fail_at=None
            raise RuntimeError("simulated:"+name)
    def verify_root_bootstrap_trust(self):self.action("verified_root_installed_source")
    @contextmanager
    def lock_existing_production_manager(self):
        self.action("locked_existing_pm")
        try:yield
        finally:self.events.append("unlock")
    def independent_live_source_ci_and_freeze(self,plan):self.action("fresh_source_ci_freeze")
    def deny_prior_attempt_or_changed_root_files(self,plan):self.action("no_pending_mutation")
    def obtain_verified_entra_owner_for_exact_action(self,plan):
        self.action("verified_entra_owner_device_flow")
        return self.auth
    def consumed_owner_approvals(self):
        self.action("replay_ledger")
        return frozenset(self.consumed)
    def journal_intent_before_mutation(self,plan,owner):self.action("journal")
    def consume_owner_approval_once(self,approval_id):
        self.action("consume_one_use_approval")
        assert approval_id not in self.consumed
        self.consumed.add(approval_id)
    def backup_original_worker_and_units(self,plan):self.action("backed_up_old_worker")
    def install_exact_root_files(self,plan):self.action("installed_root_bundle")
    def install_root_policy(self,plan):
        self.action("installed_root_policy")
        self.installed=True
    def activate_and_verify_recovery_watchdog(self,plan):self.action("timer_enabled")
    def independent_live_readback(self,plan):self.action("root_readback")
    def restore_original_worker_units_and_state(self,plan):
        self.action("rollback_old_worker_units")
        if self.rollback_broken:raise RuntimeError("rollback failed")
        self.installed=False
    def independently_verify_rollback_and_freeze(self,plan):self.action("verify_rollback_freeze")
    def open_root_production_breaker(self,reason):
        self.events.append("opened_breaker")
        self.breaker.append(reason)
    def record_completion(self,plan,outcome):self.action("outcome:"+outcome)


def test_exact_one_use_owner_install_success_and_distinct_promotion_gate(plan):
    owner=evidence(plan)
    host=FakeRoot(owner)
    receipt=t.execute_root_install_transaction(plan,host)
    assert receipt["status"]=="exact_catalog_root_install_verified"
    assert receipt["runtime_mcp_image_promotion_approved"] is False
    assert receipt["autotask_provider_write_approved"] is False
    assert host.installed is True
    assert host.events.index("journal")<host.events.index("consume_one_use_approval")
    assert host.events.index("consume_one_use_approval")<host.events.index("installed_root_bundle")
    assert host.events.index("installed_root_bundle")<host.events.index("timer_enabled")
    assert host.events.index("timer_enabled")<host.events.index("root_readback")
    assert host.events[-1]=="unlock"
    with pytest.raises(t.CatalogRootInstallDenied,match="OWNER_REPLAY"):
        t.execute_root_install_transaction(plan,host)
    assert host.events.count("installed_root_bundle")==1


@pytest.mark.parametrize("key,value",[
    ("owner_tenant","bad"),("owner_oid","deadbeef-0000-0000-0000-000000000000"),
    ("owner_principal","person-fake"),("assurance","chat_only"),
    ("scope_sha256","0"*64),("manifest_sha256","0"*64),
    ("freeze_sha256","0"*64),("source_sha","0"*40),
    ("affirmative_decision","approved"),("one_use",False),
    ("provider_write_approved",True),
])
def test_forged_identity_or_scope_denied_before_root_writes(plan,key,value):
    owner=evidence(plan)
    owner[key]=value
    host=FakeRoot(owner)
    with pytest.raises(t.CatalogRootInstallDenied,match="EXACT_OWNER_APPROVAL_SCOPE_OR_IDENTITY_INVALID"):
        t.execute_root_install_transaction(plan,host)
    assert "journal" not in host.events
    assert host.consumed==set()
    assert host.installed is False


@pytest.mark.parametrize("key,value",[
    ("source_sha","0"*40),("freeze_sha256","0"*64),
    ("installation_scope_sha256","0"*64),
    ("owner_approval_recorded",True),
    ("signed_separate_image_promotion_approval_required",False),
    ("installation_executable_in_source_only_mode",True),
])
def test_plan_tamper_denied_before_any_root_trust(plan,key,value):
    edited=deepcopy(plan)
    edited[key]=value
    host=FakeRoot(evidence(plan))
    with pytest.raises(t.CatalogRootInstallDenied):
        t.execute_root_install_transaction(edited,host)
    assert host.events==[]


@pytest.mark.parametrize("phase",[
    "verified_root_installed_source","locked_existing_pm","fresh_source_ci_freeze",
    "no_pending_mutation","verified_entra_owner_device_flow","replay_ledger","journal",
])
def test_preapproval_or_preintent_error_has_zero_production_writes(plan,phase):
    host=FakeRoot(evidence(plan),fail_at=phase)
    with pytest.raises(RuntimeError):t.execute_root_install_transaction(plan,host)
    assert host.consumed==set()
    assert "installed_root_bundle" not in host.events


@pytest.mark.parametrize("phase",[
    "installed_root_bundle","installed_root_policy",
    "timer_enabled","root_readback","outcome:exact_catalog_root_install_verified",
])
def test_partial_failure_rolls_back_old_worker_and_freeze(plan,phase):
    host=FakeRoot(evidence(plan),fail_at=phase)
    with pytest.raises(t.CatalogRootInstallDenied,match="ROLLED_BACK"):
        t.execute_root_install_transaction(plan,host)
    assert host.consumed
    assert "rollback_old_worker_units" in host.events
    assert "verify_rollback_freeze" in host.events
    assert host.installed is False


def test_unverified_root_rollback_opens_breaker(plan):
    host=FakeRoot(evidence(plan),fail_at="timer_enabled",rollback_broken=True)
    with pytest.raises(t.CatalogRootInstallDenied,match="ROLLBACK_UNVERIFIED"):
        t.execute_root_install_transaction(plan,host)
    assert host.breaker==["CATALOG_ROOT_INSTALL_ROLLBACK_UNVERIFIED"]


def test_exact_source_bundle_has_no_arbitrary_paths(plan):
    assert len(plan["root_file_plan"])==17
    assert t.verify_plan(plan)["install_plan_sha256"]==plan["install_plan_sha256"]
    modified=deepcopy(plan)
    modified["root_file_plan"][0]["destination"]="/etc/sudoers"
    with pytest.raises(t.CatalogRootInstallDenied,match="PLAN_FILE_ALLOWLIST_CHANGED"):
        t.verify_plan(modified)


def test_owner_expired_or_future_signed_jwt_receipt_denied(plan):
    for offset in (-60, 11):
        forged=evidence(plan)
        forged["approved_at"]=(datetime.now(timezone.utc)+timedelta(minutes=offset)).isoformat()
        host=FakeRoot(forged)
        with pytest.raises(t.CatalogRootInstallDenied,match="OWNER_EVIDENCE_STALE_OR_FUTURE"):
            t.execute_root_install_transaction(plan,host)
        assert "journal" not in host.events
        assert host.consumed==set()


def test_backup_failure_before_production_mutation_does_not_open_breaker(plan):
    host=FakeRoot(evidence(plan),fail_at="backed_up_old_worker")
    with pytest.raises(RuntimeError,match="backed_up_old_worker"):
        t.execute_root_install_transaction(plan,host)
    assert host.installed is False
    assert host.breaker==[]
    assert "installed_root_bundle" not in host.events
    assert "outcome:root_install_backup_failed_before_mutation" in host.events
