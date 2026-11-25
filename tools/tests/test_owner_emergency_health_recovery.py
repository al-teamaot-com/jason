"""Negative and bounded recovery tests: no fabricated full-integrity PASS."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import owner_emergency_fast_health as health
import owner_emergency_recover_nonteams as root


def quick_state() -> dict:
    return {
        "status": "fail",
        "failures": [health.ALLOWED_FAILURE],
        "files": {
            k: {"present": True, "readable": True, "mode": "0o600"}
            for k in ("authority", "replay", "security_audit", "orchestration_audit")
        },
        "delegations": {"expired_active_records": 0},
        "trusted_key_registry": {"present":True,"active_records":1,"mode":"0o600"},
    }


def test_known_full_timeout_has_only_time_bounded_degraded_result():
    now=datetime(2026,11,11,12,tzinfo=timezone.utc)
    with patch.object(health,"known_full_timeout",return_value=True):
        assert health.classify(quick_state(),now)=="degraded_read_safe"
        assert health.classify(quick_state(),health.EXPIRES+timedelta(seconds=1))=="fail"


@pytest.mark.parametrize("key,value",[
    ("failures",["unavailable_or_unsafe"]),
    ("failures",[health.ALLOWED_FAILURE,"authority_unavailable_or_unsafe"]),
    ("delegations",{"expired_active_records":1}),
    ("trusted_key_registry",{"present":False,"active_records":0,"mode":"0o600"}),
    ("files",{}),
])
def test_degradation_never_masks_real_authority_failure(key,value):
    data=quick_state()
    data[key]=value
    with patch.object(health,"known_full_timeout",return_value=True):
        assert health.classify(data,datetime(2026,11,11,12,tzinfo=timezone.utc))=="fail"


def test_bad_full_proof_does_not_degrade():
    with patch.object(health,"known_full_timeout",return_value=False):
        assert health.classify(quick_state(),
               datetime(2026,11,11,12,tzinfo=timezone.utc))=="fail"


def test_real_full_proof_is_pass_without_emergency_waiver():
    data=quick_state()
    data.update(status="pass",failures=[])
    assert health.classify(data,datetime(2026,11,15,12,tzinfo=timezone.utc))=="pass"


def test_nonroot_cannot_touch_systemctl():
    with patch.object(root.os,"geteuid",return_value=1000), \
         patch.object(root,"system",side_effect=AssertionError("must not touch systemd")):
        with pytest.raises(PermissionError,match="authenticated local sudo"):
            root.check_preconditions()


def test_recovery_has_no_runtime_restart_no_ticket_or_provider_write():
    source=Path(root.__file__).read_text()
    assert "jason-ccc" in source
    assert 'return state, frozen' in source
    assert 'ctl.verify_immutable_lkg_fingerprint(' in source
    assert 'ctl.refresh_stale_drift()' in source
    assert 'previous.recover()' in source
    assert 'ctl.apply_transition({"action":"revalidate","revision":V2}' in source
    assert 'FREEZE.read_bytes() != frozen' in source
    assert '"no_deployment":True' in source
    assert '"no_standing_release_authority":True' in source
    assert 'docker' not in source
    assert "jason-runtime.service" not in source
    assert 'system("reset-failed", unit)' in source
    assert 'system("disable"' not in source


def test_original_immutable_root_lkg_record_is_never_weakened():
    source=Path(root.__file__).read_text()
    assert "state_field(unit, \"ActiveState\") != \"failed\"" in source
    assert "ctl.verify_health(V2)" in source
    assert 'prior_state' in source
    assert 'ctl.write_json(CONTROL, prior_state, 0, 0)' in source
    assert 'changed_root_control = True' in source
    assert "status" in source
