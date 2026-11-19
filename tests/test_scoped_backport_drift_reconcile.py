"""Only four signed scoped-backport root units may be added by this action."""
import json
from pathlib import Path
import pytest

from tools import scoped_backport_drift_reconcile_root as root
from tools import scoped_backport_drift_reconcile_owner as owner
from tools import scoped_backport_drift_reconcile_builder as builder


def existing():
    return {
        "schema_version": "1.0",
        "allowed_system_units": ["jason-release-control-readback.service"],
        "required_system_units": ["jason-runtime.service"],
        "allowed_running_containers": ["jason-runtime", "jason-mcp-pilot"],
        "max_stopped_rollback_containers": 20,
        "forbidden_execution_prefixes": ["/unsafe"],
    }


def test_exact_four_unit_policy_only():
    original=existing()
    before=json.loads(json.dumps(original))
    candidate=root.expected_policy(json.dumps(original).encode())
    assert original==before
    assert set(candidate["allowed_system_units"])-set(original["allowed_system_units"])==set(root.CANDIDATE_NAMES)
    assert len(candidate["allowed_system_units"])==len(original["allowed_system_units"])+4
    assert set(candidate)==set(original)
    for key in original:
        if key!="allowed_system_units":
            assert candidate[key]==original[key]
    assert root.ACTION==owner.ACTION
    assert "owner" in owner.__doc__.lower()
    assert builder.root.ACTION==root.ACTION


@pytest.mark.parametrize("mutation",[
    lambda p: p["allowed_system_units"].append(root.CANDIDATE_NAMES[0]),
    lambda p: p.update({"max_stopped_rollback_containers":21}),
    lambda p: p.update({"max_stopped_rollback_containers":200}),
    lambda p: p["allowed_system_units"].append("jason-release-control-readback.service"),
])
def test_bad_or_already_migrated_policy_denied(mutation):
    data=existing()
    mutation(data)
    with pytest.raises(root.CatalogDriftDenied):
        root.expected_policy(json.dumps(data).encode())


def test_signed_approval_must_be_oneuse_without_restarts():
    source=Path(root.__file__).read_text()
    who=Path(owner.__file__).read_text()
    assert "verify_exact_owner_release" in source
    assert "SIGNED_OWNER_PLAN_MISMATCH" in source
    assert 'ROOT_POLICY' in source
    assert '"jason-production-drift-watchdog.service"' in source
    assert "restart_containers" in source
    assert "no_database_relocation" not in source
    assert "owner_consents" in who
    assert "C_OWNER_PROOF_PERSISTENCE_FAILED" not in who
    assert "SCOPED_BACKPORT_DRIFT_OWNER_PROOF_PERSISTENCE_FAILED" in who
    assert "TICKET_CORE_AND_MCP_UNCHANGED=true" in who


def test_no_change_to_freeze_core_mcp_breaker_or_catalog_timers():
    code=Path(root.__file__).read_text()
    assert "systemctl\",\"start\"" in code
    assert "jason-production-drift-watchdog.service" in code
    for verb in ('["/usr/bin/systemctl","disable"', '["/usr/bin/systemctl","enable"',
                 '["/usr/bin/systemctl","restart"', '["/usr/bin/docker","stop"',
                 '["/usr/bin/docker","restart"', '["/usr/bin/systemctl","mask"'):
        assert verb not in code
    assert "revalidate_circuit_breaker" in code
    assert "SCOPED_BACKPORT_FOUR_UNIT_DRIFT_POLICY_RECONCILED=PASS" in code


def test_root_policy_target_does_not_relax_drift_guards():
    base=existing()
    base.update({
        "allowed_user_units":["jason-release-manager.service"],
        "required_user_units":["jason-release-manager.timer"],
        "max_stopped_rollback_containers":20,
        "required_containers":["jason-runtime","jason-mcp-pilot"],
    })
    new=root.expected_policy(json.dumps(base).encode())
    for key in ("forbidden_execution_prefixes","required_containers",
                "max_stopped_rollback_containers","required_system_units",
                "required_user_units","allowed_user_units"):
        assert new[key]==base[key]


def test_root_write_uses_root_protected_baseline_not_mutable_packet_bytes():
    source=Path(root.__file__).read_text()
    section=source.split("def apply(path):",1)[1]
    before_commit=section.split("atomic_policy(candidate)",1)[0]
    assert "candidate=(json.dumps(expected_policy(baseline)" in before_commit
    assert 'baseline=file_bytes(ROOT_POLICY,mode=0o600)' in before_commit
    assert 'plan["candidate_policy_sha256"]' in before_commit
    assert '(packet.parent/"candidate.json").read_bytes()' not in before_commit
    assert 'with lock_transaction():' in before_commit


def test_no_direct_breaker_state_edits_or_guard_bypass():
    code=Path(root.__file__).read_text()
    assert "revalidate_circuit_breaker" in code
    assert 'trusted.revalidate_circuit_breaker(' in code
    assert '"NATIVE_BREAKER_NOT_CLOSED"' in code
    assert '"root_scoped_backport_four_unit_allowlist"' in code
    assert '"breaker_override":False' in code
    assert '"scoped_backport_unit_names"' in code
    assert '"jason-production-drift-watchdog.service"' in code
    assert '"jason-scoped-backport-recovery.timer"' in code
    assert '"jason-scoped-backport-requests.path"' in code
    assert '"root_scoped_backport_four_unit_allowlist"' in Path(builder.__file__).read_text()
