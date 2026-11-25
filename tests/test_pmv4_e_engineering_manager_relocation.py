"""Source-only tests: no real scheduler, provider, or production mutation."""
from pathlib import Path
from copy import deepcopy
import pytest
from tools import pmv4_e_engineering_manager_relocation as m

ROOT = Path(__file__).resolve().parents[1]


def policy():
    return {"schema_version": "1.0",
            "required_user_units": [m.TIMER, "jason-self-heal-watchdog.timer"],
            "required_system_units": ["jason-core.service"],
            "allowed_user_units": [m.SERVICE, "jason-support-repair-worker.service"],
            "allowed_system_units": ["jason-runtime.service"],
            "required_containers": ["jason-runtime", "jason-pmv4-ticket-core"],
            "forbidden_execution_prefixes": ["forbidden"]}


def test_candidate_is_exact_and_retains_sandbox_and_original_guards():
    files = m.units(ROOT)
    assert len(files) == 2
    for name, data in files.items():
        assert (ROOT / name).read_bytes() == data
    old = (ROOT / m.SOURCE / m.SERVICE).read_text()
    new = files[str(m.TARGET / m.SERVICE)].decode()
    assert "User=al\nGroup=al\n" in new
    assert "ConditionPathExists=" + m.ROOT_RECEIPT in new
    assert "ConditionPathExists=!" + m.PAUSE in new
    assert "ExecCondition=/usr/bin/python3 -I -B " + m.SUCCESSOR_GUARD in new
    assert "ExecCondition=+" not in new and "ExecStart=+" not in new
    for line in old.splitlines():
        if line.startswith(("ExecCondition=", "ExecStart=", "NoNewPrivileges=", "PrivateTmp=",
                            "ProtectSystem=", "ProtectHome=", "WorkingDirectory=", "TimeoutStartSec=")):
            assert line in new.splitlines()
    old_rw = next(x for x in old.splitlines() if x.startswith("ReadWritePaths="))
    new_rw = next(x for x in new.splitlines() if x.startswith("ReadWritePaths="))
    assert new_rw == old_rw.replace("ReadWritePaths=", "ReadWritePaths=" + m.GIT_METADATA + " ", 1)
    assert files[str(m.TARGET / m.TIMER)] == (ROOT / m.SOURCE / m.TIMER).read_bytes()


def test_exact_policy_delta_is_nonmutating_and_preserves_other_controls():
    before = policy()
    saved = deepcopy(before)
    out = m.desired_state_delta(before)
    assert before == saved
    assert set(out["required_user_units"]) == set(before["required_user_units"]) - {m.TIMER}
    assert set(out["required_system_units"]) == set(before["required_system_units"]) | {m.TIMER}
    assert set(out["allowed_user_units"]) == set(before["allowed_user_units"]) - {m.SERVICE}
    assert set(out["allowed_system_units"]) == set(before["allowed_system_units"]) | {m.SERVICE}
    assert out["required_containers"] == before["required_containers"]
    assert out["forbidden_execution_prefixes"] == before["forbidden_execution_prefixes"]


@pytest.mark.parametrize("field,value", [
    ("required_user_units", []),
    ("required_system_units", [m.TIMER]),
    ("allowed_user_units", [m.SERVICE, m.SERVICE]),
    ("allowed_system_units", [m.SERVICE]),
    ("allowed_user_units", [m.SERVICE, m.TIMER]),
    ("required_system_units", [m.SERVICE]),
])
def test_conflicting_or_ambiguous_policy_is_denied(field, value):
    p = policy()
    p[field] = value
    with pytest.raises(ValueError, match="ENGINEERING_MANAGER_RELOCATION_"):
        m.desired_state_delta(p)


def test_source_plan_does_not_grant_authority():
    p = m.routing_plan(base=ROOT, policy=policy())
    assert p["production_changes_performed"] is False
    assert p["owner_authority_issued"] is False
    assert p["original_pause_preserved_during_install"] is True
    assert p["require_legacy_timer_and_service_retired"] is True
    assert p["require_root_owned_successor_guard_and_receipt"] is True
    assert p["require_manager_aware_manifest_and_watchdog"] is True
