"""P0 #1974: reject root-policy/immutable-source mismatches before host writes."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "release_host_reconcile_worker.py"
spec = importlib.util.spec_from_file_location("host_root_policy_gate_1974", SCRIPT)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

SHA = "e8caace9791659adfd383a7ff148253c2ac5f424"
OLD = {
    "schema_version": "1.0",
    "required_system_units": ["jason-openclaw-authority-health.timer"],
    "allowed_system_units": ["jason-openclaw-authority-health.service"],
    "required_user_units": ["jason-release-manager.timer"],
    "allowed_user_units": ["jason-release-manager.service"],
}
NEW = {
    **OLD,
    "required_system_units": OLD["required_system_units"] + [
        "jason-openclaw-authority-full-integrity.timer"
    ],
    "allowed_system_units": OLD["allowed_system_units"] + [
        "jason-openclaw-authority-full-integrity.service"
    ],
}


def checked(candidate: dict, root: dict):
    with patch.object(
        worker.subprocess, "check_output", return_value=json.dumps(candidate)
    ) as show, patch.object(
        worker, "_protected_root_drift_policy", return_value=root
    ):
        worker._verify_root_policy_covers_candidate(SHA)
    args = show.call_args.args[0]
    assert args[-2:] == [
        "show", f"{SHA}:config/production-desired-state.json"
    ]


def test_missing_new_integrity_timer_and_service_are_rejected_before_install():
    with pytest.raises(worker.HostReconcileError) as err:
        checked(NEW, OLD)
    msg = str(err.value)
    assert "required_system_units:jason-openclaw-authority-full-integrity.timer" in msg
    assert "allowed_system_units:jason-openclaw-authority-full-integrity.service" in msg
    assert "authorized root-policy migration" in msg
    assert "before host mutation" in msg


def test_exact_root_migration_allows_candidate_without_permissive_fallback():
    checked(NEW, NEW)
    # Extra already-approved root-only recovery units may remain, but not
    # substitute for any missing required timer declaration.
    compatible = {
        **NEW,
        "allowed_system_units": NEW["allowed_system_units"] + [
            "jason-release-control-readback.service"
        ],
    }
    checked(NEW, compatible)


def test_merely_allowed_timer_does_not_satisfy_required_timer():
    root = {
        **OLD,
        "allowed_system_units": OLD["allowed_system_units"] + [
            "jason-openclaw-authority-full-integrity.timer",
            "jason-openclaw-authority-full-integrity.service",
        ],
    }
    with pytest.raises(worker.HostReconcileError) as err:
        checked(NEW, root)
    assert "required_system_units:jason-openclaw-authority-full-integrity.timer" in str(err.value)


@pytest.mark.parametrize(
    "invalid",
    [
        {"schema_version": "1.0", "required_system_units": ["jason-bad.service"]},
        {**NEW, "allowed_system_units": ["jason-a.service", "jason-a.service"]},
        {**NEW, "required_user_units": ["../../root"]},
        {**NEW, "required_user_units": [42]},
    ],
)
def test_incomplete_or_malformed_policy_fails_closed(invalid):
    with pytest.raises(worker.HostReconcileError):
        checked(NEW, invalid)


def test_root_policy_must_be_root_owned_and_private(tmp_path):
    policy = tmp_path / "root-policy.json"
    policy.write_text(json.dumps(NEW))
    policy.chmod(0o600)
    with patch.object(worker, "ROOT_RECOVERY_POLICY", policy):
        if policy.stat().st_uid != 0:
            with pytest.raises(worker.HostReconcileError, match="root-only"):
                worker._protected_root_drift_policy()
        else:
            assert worker._protected_root_drift_policy() == NEW


def test_root_policy_gate_precedes_candidate_host_shell_execution():
    code = SCRIPT.read_text(encoding="utf-8")
    start = code.index("def _process(")
    preflight = code.index("_preflight_candidate_root_policy(source_revision)", start)
    candidate_script = code.index("_candidate_reconcile_script(source_revision)", start)
    after_install = code.index("_verify_root_policy_covers_candidate(source_revision)", candidate_script)
    success_result = code.index("_write_result(", after_install)
    assert preflight < candidate_script < after_install < success_result
    assert 'if policy_preflight != "ALREADY_COVERED":' in code
    assert "requires separately authorized root-policy migration" in code
