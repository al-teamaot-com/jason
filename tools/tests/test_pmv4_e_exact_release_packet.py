"""Source scope digest and protected evidence denial for PMv4 Stage E."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from tools import pmv4_e_exact_release_packet as packet

GOOD="b"*40
OLD="a"*40


def test_exact_scoped_bundle_contains_reviewed_source_and_two_unit_sets():
    p=packet.prepare(candidate_sha=GOOD,rollback_sha=OLD)
    assert p["status"]=="source_packet_pending_independent_root_acceptance"
    assert p["reviewed_systemd_new_files"]==12
    assert p["reviewed_systemd_old_inputs"]==12
    assert p["reviewed_files"]==len(packet.REVIEWED_PATHS)
    assert len(p["source_scope_sha256"])==64
    assert len(p["source_manifest_sha256"])==64
    assert p["production_release_ready"] is False
    assert p["signed_owner_proof"] is None
    assert p["production_mutations"] is False
    assert p["owner_authority_issued"] is False
    assert p["protected_root_policy_verified"] is False
    assert p["freeze_verified"] is False


def test_repeated_packet_is_deterministic_and_changing_candidate_changes_scope():
    a=packet.prepare(candidate_sha=GOOD,rollback_sha=OLD)
    b=packet.prepare(candidate_sha=GOOD,rollback_sha=OLD)
    assert a==b
    c=packet.prepare(candidate_sha="c"*40,rollback_sha=OLD)
    assert c["source_scope_sha256"]!=a["source_scope_sha256"]
    assert c["source_manifest_sha256"]!=a["source_manifest_sha256"]


def test_reviewed_scope_includes_watchdog_and_native_bridge_but_no_runtime_restart():
    a=packet.prepare(candidate_sha=GOOD,rollback_sha=OLD)
    paths=a["source_scope"]["exact_replacement_files_sha256"]
    assert "tools/pmv4_e_native_backend_bridge.py" in paths
    assert "tools/pmv4_e_systemd_root_ops.py" in paths
    assert "tools/jason_self_heal_watchdog.py" in paths
    assert "tools/release_manager_host_runner.py" in paths
    assert "tools/reconcile_production_host_services.sh" in paths
    assert a["source_scope"]["protected_runtime_mcp_restart_allowed"] is False
    assert a["source_scope"]["provider_writes_allowed"] is False


@pytest.mark.parametrize("candidate,rollback",[
    ("notsha",OLD),(GOOD,GOOD),("0"*39,OLD),(GOOD,"z"*40),
])
def test_wrong_candidate_or_rollback_denied(candidate,rollback):
    with pytest.raises(packet.StageEReleasePacketDenied):
        packet.prepare(candidate_sha=candidate,rollback_sha=rollback)


def test_missing_required_unit_source_denied(tmp_path):
    source=packet.ROOT
    small=tmp_path/"isolated"
    small.mkdir()
    with pytest.raises(packet.StageEReleasePacketDenied):
        packet.prepare(root=small,candidate_sha=GOOD,rollback_sha=OLD)


def test_root_hash_claims_do_not_issue_authority_even_with_matching_strings():
    a=packet.prepare(candidate_sha=GOOD,rollback_sha=OLD,
        observed_root_policy_sha256=packet.EXPECTED_PRIOR_ROOT_POLICY,
        observed_freeze_sha256=packet.EXPECTED_FREEZE)
    assert a["protected_root_policy_verified"] is True
    assert a["freeze_verified"] is True
    assert a["owner_authority_issued"] is False
    assert a["production_release_ready"] is False
    assert a["signed_owner_proof"] is None
