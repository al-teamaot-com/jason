"""Exact canonical-host recovery release: only synthetic/source checks.

NEVER operates on real root units, live SQLite or the production breaker.
"""
from __future__ import annotations
from pathlib import Path
import os
import stat
import inspect
from unittest.mock import Mock
import pytest
from tools import pmv4_c_host_recovery_builder as builder
from tools import pmv4_c_host_recovery_owner as owner
from tools import pmv4_c_host_recovery_root as root

def test_service_scope_is_exactly_two_health_and_five_existing_exporters():
    assert len(builder.EXPORTERS)==5 and len(builder.HEALTH)==2
    assert root.EXPORTERS==builder.EXPORTERS
    assert root.UNITS==builder.HEALTH
    assert set(builder.drops())==set(builder.EXPORTERS)|set(builder.HEALTH)

def test_approved_root_emergency_and_full_integrity_are_preserved_by_dropins():
    docs=builder.drops()
    for name in builder.HEALTH:
        rendered=docs[name].decode()
        assert rendered.count("ExecStart=")==2
        assert "pmv4-c-canonical-health-v1/pmv4_c_authority_health_adapter.py" in rendered
        assert "/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3" in rendered
        assert "jason-runtime" not in rendered
        assert "reset-failed" not in rendered
    assert " --mode full" in docs[builder.HEALTH[1]].decode()
    assert "TimeoutStartSec=5700" in docs[builder.HEALTH[1]].decode()
    assert "ReadWritePaths=/var/lib/jason/governed-ticket-shared" in docs[builder.HEALTH[1]].decode()
    assert "ReadWritePaths=/var/lib/jason/governed-ticket-shared" not in docs[builder.HEALTH[0]].decode()
    assert " --mode fast" in docs[builder.HEALTH[0]].decode()

def test_authority_full_proof_is_persistent_native_systemd_not_fake_pass():
    source=inspect.getsource(root.execute)
    assert "start" in source and '"--no-block"' in source
    assert "full_proof_started_pending" in source
    assert "FULL_INTEGRITY=STARTED_NOT_YET_VERIFIED" in source
    assert "PRODUCTION_BREAKER_RESET=false" in source
    assert "reset-failed" not in source
    assert "stop\",\"jason-runtime\"" not in source
    assert "jason-pmv4-ticket-core" not in source

def test_new_root_has_no_untrusted_staged_python_import_at_module_init():
    source=Path(root.__file__).read_text()
    pre=source.split("class HostRecoveryDenied",1)[0]
    assert "sys.path.insert" not in pre
    assert "from tools import" not in pre
    assert "CI_PIN=Path(\"/opt/jason/current/tools/pmv4_shadow_ci.py\")" in pre
    assert "HOST_RECOVERY_PROTECTED_MAIN_CI_NOT_VERIFIED" in source
    assert "HOST_RECOVERY_PREVIOUS_OWNER_SIGNATURE_INVALID" in source

def test_required_lock_order_and_explicit_breaker_fault():
    assert root.LOCKS[0].name=="production-transaction.lock"
    assert root.LOCKS[1].name=="host-mutation.lock"
    source=inspect.getsource(root.active_state)
    assert 'circuit.get("state")=="open"' in source
    assert '"continuous_production_drift_detected"' in source
    assert '"jason-openclaw-authority-health.service"' in source
    assert "HOST_RECOVERY_BREAKER_OR_DRIFT_NOT_EXACT" in source
    assert "HOST_RECOVERY_CANONICAL_INODE_CHANGED" in source

def test_root_rejects_nonprivileged_without_reading_files(tmp_path,monkeypatch):
    p=tmp_path/"plan.json"
    p.write_text('{"schema_version":"1.0"}')
    monkeypatch.setattr(root.os,"geteuid",lambda:1000)
    with pytest.raises(root.HostRecoveryDenied,match="PRIVILEGED_ROOT_REQUIRED"):
        root.exact_plan(p)

def test_owner_issuer_binds_same_action_and_both_accounts(tmp_path):
    assert owner.ACTION==root.ACTION==builder.ACTION
    assert owner.CONFIRM=="APPROVE-ONE-EXACT-PMV4-C-HOST-HEALTH-RECOVERY"
    if not owner.OWNER_SIGNER.is_file():
        pytest.skip("Installed root-pinned native signer absent on GitHub CI runner")
    signer=owner.trusted(owner.OWNER_SIGNER,owner.OWNER_SIGNER_SHA,"host_test_signer")
    plan={
        "candidate_sha":"a"*40,"rollback_sha":root.LKG,"scope_sha256":"b"*64,
        "freeze_sha256":"c"*64
    }
    owner.signer_contract_preflight(signer,plan)
    assert len(signer.EXACT_OWNER_OAUTH_SUBJECTS)==2
    assert owner.release_id(plan)=="release-"+"a"*16

def test_expired_emergency_override_not_extended_by_recovery():
    source=Path(root.__file__).read_text()
    assert "91-owner-emergency-full-proof-degraded.conf" not in inspect.getsource(root.execute)
    assert root.HEALTH_DROPIN.startswith("99-")
    assert "owner_emergency_fast_health.py" not in inspect.getsource(root.execute)

def test_unrecognized_install_target_blocked(tmp_path):
    target=tmp_path/"existing"
    target.write_bytes(b"sentinel")
    with pytest.raises(root.HostRecoveryDenied,match="INSTALL_COLLISION"):
        root.install_bytes(target,b"different")
    assert target.read_bytes()==b"sentinel"

def test_synthetic_installer_does_not_write_when_plan_untrusted(monkeypatch,tmp_path):
    monkeypatch.setattr(root.os,"geteuid",lambda:1000)
    path=tmp_path/"bad.json"
    path.write_text('{"schema_version":"1.0","action":"wrong"}')
    with pytest.raises(root.HostRecoveryDenied):
        root.preflight(path)
    assert sorted(p.name for p in tmp_path.iterdir())==["bad.json"]

def test_builder_denies_unmerged_or_modified_source(monkeypatch):
    # Stub external calls, never write root state or request an Owner login.
    monkeypatch.setattr(builder,"call",lambda args:"a"*40 if
                         args[0] == "/usr/bin/git" else "b"*40)
    with pytest.raises(RuntimeError,match="SOURCE_NOT_MAIN"):
        builder.build()

def test_immutable_owner_approval_cannot_reuse_failed_stage_c_scope():
    source=inspect.getsource(owner.exact_plan)
    assert "previous_stage_c_sha" in source
    assert "no_database_relocation" in source
    assert "requires_genuine_canonical_full_proof" in source
    assert "service_restarts" in source
    assert "two_scan_acceptance" not in source

def test_real_scans_required_for_external_stage_c_separate_from_host_repair():
    source=inspect.getsource(root.execute)
    assert "INDEPENDENT_TICKET_WORKER_ACTIVATED=false" in source
    assert "OWNER_APPROVAL" not in source or "OWNER_APPROVAL" in inspect.getsource(root.verify_owner)
    assert root.STAGE_C=="13917410bb0ea1d5d37a314b3a3f131d416bf154"
